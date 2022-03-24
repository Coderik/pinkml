import itertools
import logging
import math
import re
import sys
from typing import Optional, Dict, List, Tuple
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

from . import NAMESPACE_MAPPING as NS
from . import ink as Ink, reading_types as rt, inkml
from .ids import is_local_id, to_local_id
from .references import resolve_references


class Reader:
	def __init__(self,
	             assume_local_refs: bool = False,
	             logger: Optional[logging.RootLogger] = None):
		self.assume_local_refs = assume_local_refs

		if not isinstance(logger, logging.RootLogger):
			logger = logging.getLogger('inkml')
			logger.setLevel(logging.INFO)

			info_handler = logging.StreamHandler(stream=sys.stdout)
			info_handler.addFilter(lambda record: record.levelno == logging.INFO)
			info_handler.setFormatter(logging.Formatter('%(message)s'))
			logger.addHandler(info_handler)

			warn_handler = logging.StreamHandler(stream=sys.stdout)
			warn_handler.addFilter(lambda record: record.levelno == logging.WARNING)
			warn_handler.setFormatter(logging.Formatter('WARNING. %(message)s'))
			logger.addHandler(warn_handler)

		self.logger = logger

		# RegEx to split a point of a trace into tokens (Sec. 3.2.1 of https://www.w3.org/TR/2011/REC-InkML-20110920/)
		self.tokenize_expr = \
			re.compile(r'((?:[!\'"]?\s*-?\s*(?:(?:\d+(?:\.\d*)?|(\.\d+))([eE][+-]?\d)?)|(#[\dA-F]+))|[TF*?])')

	def read(self, content: str) -> Ink.Ink:
		# Parse raw string content
		try:
			root: Element = ElementTree.fromstring(content)
		except ElementTree.ParseError as e:
			raise Exception('Could not parse InkML content')

		# Get root element which is supposed to be <ink xmlns="http://www.w3.org/2003/InkML">
		if root.tag != inkml.INK:
			raise Exception('Unexpected root element: {}'.format(root.tag))

		definitions = self.read_definitions(root)
		resolve_references(definitions, self.assume_local_refs)

		# TODO: resolve channel.respectTo for time channels

		ink = Ink.Ink()

		# Read traces and traceGroups (no 'current' context in archival mode)
		ink.traces = self.read_traces(root, definitions, None)

		# Read top-level annotations
		ink.annotations = self.read_annotations(root)

		# Move definitions
		ink.definitions.contexts = [env.context for env in definitions.contexts.values()]
		ink.definitions.brushes = [env.brush for env in definitions.brushes.values()]
		ink.definitions.ink_sources = [v for v in definitions.ink_sources.values()]
		ink.definitions.trace_formats = [v for v in definitions.trace_formats.values()]
		ink.definitions.timestamps = [env.timestamp for env in definitions.timestamps.values()]

		return ink

	def read_definitions(self, root: Element) -> rt.Definitions:
		definitions = rt.Definitions()

		# Get all <definitions> elements
		definitions_elements = root.findall('inkml:definitions', namespaces=NS)

		# Find and store all <inkSource>, <brush>, <traceFormat> and <parent> elements within definitions
		for element in definitions_elements:
			# Read <inkSource> elements
			ink_source_elements = element.findall('inkml:inkSource', namespaces=NS)
			for ink_source_element in ink_source_elements:
				ink_source = self.read_ink_source(ink_source_element)
				if ink_source is None:
					continue   # skip invalid inkSource

				definitions.ink_sources[ink_source.id] = ink_source

				if len(ink_source.trace_format.id) > 0:
					definitions.trace_formats[ink_source.trace_format.id] = ink_source.trace_format

			# Read <brush> elements
			brush_elements = element.findall('inkml:brush', namespaces=NS)
			for brush_element in brush_elements:
				brush = self.read_brush(brush_element)
				if len(brush.id) == 0:
					continue   # skip brush without ID

				definitions.brushes[brush.id] = brush

			# Read <traceFormat> elements
			trace_format_elements = element.findall('inkml:traceFormat', namespaces=NS)
			for trace_format_element in trace_format_elements:
				trace_format = self.read_trace_format(trace_format_element)
				if len(trace_format.id) == 0:
					continue   # skip traceFormat without ID

				definitions.trace_formats[trace_format.id] = trace_format

			# Read <timestamp> elements
			timestamp_elements = element.findall('inkml:timestamp', namespaces=NS)
			for timestamp_element in timestamp_elements:
				timestamp = self.read_timestamp(timestamp_element)
				if timestamp is None:
					continue   # skip invalid timestamp

				definitions.timestamps[timestamp.id] = timestamp

		# Find and store all <context> elements within definitions
		for element in definitions_elements:
			context_elements = element.findall('inkml:context', namespaces=NS)
			for context_element in context_elements:
				context = self.read_context(context_element)
				if len(context.id) == 0:
					continue   # skip context without ID

				definitions.contexts[context.id] = context

		# Find and store all <context> elements outside of definitions
		context_elements = root.findall('inkml:context', namespaces=NS)
		for context_element in context_elements:
			context = self.read_context(context_element)
			if len(context.id) == 0:
				# NOTE: in archival applications traces always reference context information explicitly
				#	   and never through the "current" context. So, contexts without IDs are ignored.
				definitions.contexts[context.id] = context

		# Keep track of data items which are specified inside contexts and have an ID
		for context in definitions.contexts.values():
			if isinstance(context.ink_source_or_ref, Ink.InkSource) and len(context.ink_source_or_ref.id) > 0 and \
					context.ink_source_or_ref.id not in definitions.ink_sources:
				definitions.ink_sources[context.ink_source_or_ref.id] = context.ink_source_or_ref

			if isinstance(context.trace_format_or_ref, Ink.TraceFormat) and len(context.trace_format_or_ref.id) > 0 and \
					context.trace_format_or_ref.id not in definitions.trace_formats:
				definitions.trace_formats[context.trace_format_or_ref.id] = context.trace_format_or_ref

			if isinstance(context.brush_or_ref, rt.BrushEnvelope) and len(context.brush_or_ref.id) > 0 and \
					context.brush_or_ref.id not in definitions.brushes:
				definitions.brushes[context.brush_or_ref.id] = context.brush_or_ref

			if isinstance(context.timestamp_or_ref, rt.TimestampEnvelope) and len(context.timestamp_or_ref.id) > 0 and \
					context.timestamp_or_ref.id not in definitions.timestamps:
				definitions.timestamps[context.timestamp_or_ref.id] = context.timestamp_or_ref

		# Find and store all <trace>, <traceGroup> and <traceView> elements within definitions
		for element in definitions_elements:
			# NOTE: traces, groups and views with IDs are stored in definitions as side-effect of readTraces(...)
			self.read_traces(element, definitions, None)

		return definitions

	def read_ink_source(self, element: Element) -> Optional[Ink.InkSource]:
		"""
		Read content of <inkSource> element.
		:param element: Element to be read
		"""
		# Get required ID attribute
		id = self.get_id(element)
		if id is None:
			self.logger.warning('Attribute "xml:id" is required for inkSource element')
			return None

		# Read required <traceFormat> child
		trace_format_element = element.find('inkml:traceFormat', namespaces=NS)
		if trace_format_element is None:
			self.logger.warning('Nested traceFormat element is required for inkSource elements')
			return None
		trace_format = self.read_trace_format(trace_format_element)

		# Create new InkSource
		ink_source = Ink.InkSource(id, trace_format)

		# Read optional nested elements
		ink_source.sampleRate = self.read_sample_rate(element.find('inkml:sampleRate', namespaces=NS))
		ink_source.latency = self.read_latency(element.find('inkml:latency', namespaces=NS))
		ink_source.activeArea = self.read_active_area(element.find('inkml:activeArea', namespaces=NS))

		# Read source properties
		source_property_elements = element.findall('inkml:sourceProperty', namespaces=NS)
		for source_property_element in source_property_elements:
			source_property = self.read_source_property(source_property_element)
			if source_property is not None:
				ink_source.properties[source_property.name] = Ink.Property(source_property.value, source_property.units)

		# Read channel properties
		channel_properties: Dict[str, List[rt.ChannelProperty]] = dict()
		channel_properties_element = element.find('inkml:channelProperties', namespaces=NS)
		if channel_properties_element is not None:
			channel_property_elements = channel_properties_element.find('inkml:channelProperty', namespaces=NS)
			for channel_property_element in channel_property_elements:
				channel_property = self.read_channel_property(channel_property_element)
				if channel_property is not None:
					if channel_property.channel in channel_properties:
						channel_properties[channel_property.channel].append(channel_property)
					else:
						channel_properties[channel_property.channel] = [channel_property]

		# Assign channel properties to corresponding channels
		for channel in itertools.chain(trace_format.regular_channels, trace_format.intermittent_channels):
			if channel.name in channel_properties:
				props = channel_properties[channel.name]
				for prop in props:
					channel.properties[prop.name] = Ink.Property(prop.value, prop.units)

		# Get remaining attributes
		ink_source.manufacturer = element.get('manufacturer')
		ink_source.model = element.get('model')
		ink_source.serialNo = element.get('serialNo')
		ink_source.specificationRef = element.get('specificationRef')
		ink_source.description = element.get('description')

		return ink_source

	def read_brush(self, element: Element) -> rt.BrushEnvelope:
		"""
		Read content of <brush> element.
		:param element: Element to be read
		"""
		envelope = rt.BrushEnvelope()

		# Get optional ID attribute
		id = self.get_id(element)
		if id is not None and len(id) > 0:
			envelope.brush.id = id

		# Get optional brushRef attribute
		brush_ref = element.get('brushRef')
		if brush_ref is not None and len(brush_ref) > 0:
			envelope.parent_ref = brush_ref

		# Read brush properties
		brush_property_elements = element.findall('inkml:brushProperty', namespaces=NS)
		for brush_property_element in brush_property_elements:
			brush_property = self.read_brush_property(brush_property_element)
			if brush_property is not None:
				envelope.brush.properties[brush_property.name] = Ink.AnnotatedProperty(brush_property.value,
				                                                                       brush_property.units,
				                                                                       brush_property.annotations)

		# Read annotations
		envelope.brush.annotations = self.read_annotations(element)

		return envelope

	def read_trace_format(self, element: Element) -> Ink.TraceFormat:
		"""
		Read content of <traceFormat> element.
		:param element: Element to be read
		"""
		trace_format = Ink.TraceFormat()

		# Get optional ID attribute
		id = self.get_id(element)
		if id is not None and len(id) > 0:
			trace_format.id = id

		# Read regular channels
		channel_elements = element.findall('inkml:channel', namespaces=NS)
		for channel_element in channel_elements:
			channel = self.read_channel(channel_element)
			if channel is not None:
				trace_format.regular_channels.append(channel)

		# Read intermittent channels
		intermittent_channels_element = element.find('inkml:intermittentChannels', namespaces=NS)
		if intermittent_channels_element is not None:
			channel_elements = intermittent_channels_element.findall('inkml:channel', namespaces=NS)
			for channel_element in channel_elements:
				channel = self.read_channel(channel_element)
				if channel is not None:
					trace_format.intermittent_channels.append(channel)

		return trace_format

	def read_channel(self, element: Element) -> Optional[Ink.Channel]:
		"""
		Read content of <channel> element.
		:param element: Element to be read
		"""
		# Get required 'name' attribute
		name = element.get('name')
		if name is None:
			self.logger.warning('Attribute "name" is required for channel element')
			return None

		channel = Ink.Channel(name)

		# Get optional ID attribute
		id = self.get_id(element)
		if id is not None and len(id) > 0:
			channel.id = id

		# Get optional type attribute
		type = element.get('type')
		if type == 'integer':
			channel.type = Ink.ChannelType.Integer
		elif type == 'decimal':
			channel.type = Ink.ChannelType.Decimal
		elif type == 'double':
			channel.type = Ink.ChannelType.Double
		elif type == 'boolean':
			channel.type = Ink.ChannelType.Boolean

		# Get optional default attribute
		default_str = element.get('default')
		if default_str is not None:
			if channel.type == Ink.ChannelType.Boolean:
				default_str = default_str.lower()
				channel.default = default_str == 'true' or default_str == 't' or default_str == '1'
			else:
				try:
					channel.default = float(default_str)
				except ValueError:
					channel.default = 0.0

		# Get optional min attribute
		min_str = element.get('min')
		if min_str is not None:
			try:
				channel.min = float(min_str)
			except ValueError:
				pass

		# Get optional max attribute
		max_str = element.get('max')
		if max_str is not None:
			try:
				channel.max = float(max_str)
			except ValueError:
				pass

		# Get optional orientation attribute
		orientation = element.get('orientation')
		if orientation == '+ve':
			channel.orientation = Ink.ChannelOrientation.Positive
		elif orientation == '-ve':
			channel.orientation = Ink.ChannelOrientation.Negative

		# Get optional respectTo attribute
		respect_to = element.get('respectTo')
		if respect_to is not None:
			channel.respectTo = respect_to

		# Get optional units attribute
		units = element.get('units')
		if units is not None:
			channel.units = units

		# TODO: Read mapping elements

		return channel

	def read_timestamp(self, element: Element) -> Optional[rt.TimestampEnvelope]:
		"""
		Read content of <timestamp> element.
		:param element: Element to be read
		"""
		# Get required ID attribute
		id = self.get_id(element)
		if id is None:
			self.logger.warning('Attribute "xml:id" is required for parent element')
			return None

		envelope = rt.TimestampEnvelope(id)

		# Get optional time attribute
		time_str = element.get('time')
		if time_str is not None:
			try:
				time = float(time_str)
				envelope.timestamp.time = time
				return envelope  # if time attribute is present, everything else is ignored
			except ValueError:
				pass

		# Get optional timeString attribute
		time_string = element.get('timeString')
		if time_string is not None:
			envelope.timestamp.timeString = time_string
			return envelope	   # if timeString attribute is present, everything else is ignored

		# Get optional timestampRef attribute
		timestamp_ref = element.get('timestampRef')
		if timestamp_ref is not None:
			envelope.parent_ref = timestamp_ref

		# Get optional timeOffset attribute
		time_offset_str = element.get('timeOffset')
		if time_offset_str is not None:
			try:
				envelope.timestamp.timeOffset = float(time_offset_str)
			except ValueError:
				pass

		return envelope

	def read_context(self, element: Element) -> rt.ContextEnvelope:
		"""
		Read content of <context> element.
		:param element: Element to be read
		"""
		envelope = rt.ContextEnvelope()

		# Get optional ID attribute
		id = self.get_id(element)
		if id is not None and len(id) > 0:
			envelope.context.id = id

		# Get optional contextRef attribute
		context_ref = element.get('contextRef')
		if context_ref is not None and len(context_ref) > 0:
			envelope.parent_ref = context_ref

		# Get optional traceFormatRef attribute
		trace_format_ref = element.get('traceFormatRef')
		if trace_format_ref is not None and len(trace_format_ref) > 0:
			envelope.trace_format_or_ref = trace_format_ref

		# Get optional inkSourceRef attribute
		ink_source_ref = element.get('inkSourceRef')
		if ink_source_ref is not None and len(ink_source_ref) > 0:
			envelope.ink_source_or_ref = ink_source_ref

		# Get optional brushRef attribute
		brush_ref = element.get('brushRef')
		if brush_ref is not None and len(brush_ref) > 0:
			envelope.brush_or_ref = brush_ref

		# Get optional timestampRef attribute
		timestamp_ref = element.get('timestampRef')
		if timestamp_ref is not None and len(timestamp_ref) > 0:
			envelope.timestamp_or_ref = timestamp_ref

		# Read traceFormat child
		trace_format_element = element.find('inkml:traceFormat', namespaces=NS)
		if trace_format_element is not None:
			envelope.trace_format_or_ref = self.read_trace_format(trace_format_element)

		# Read inkSource child
		ink_source_element = element.find('inkml:inkSource', namespaces=NS)
		if ink_source_element is not None:
			ink_source = self.read_ink_source(ink_source_element)
			if ink_source is not None:
				envelope.ink_source_or_ref = ink_source

		# Read brush child
		brush_element = element.find('inkml:brush', namespaces=NS)
		if brush_element is not None:
			envelope.brush_or_ref = self.read_brush(brush_element)

		# Read timestamp child
		timestamp_element = element.find('inkml:timestamp', namespaces=NS)
		if timestamp_element is not None:
			timestamp = self.read_timestamp(timestamp_element)
			if timestamp is not None:
				envelope.timestamp_or_ref = timestamp

		return envelope

	def read_sample_rate(self, element: Optional[Element]) -> Optional[Ink.SampleRate]:
		"""
		Read content of <sampleRate> element.
		:param element: Element to be read
		"""
		if element is None:
			return None

		# Get required 'value' attribute
		value_str = element.get('value')
		if value_str is None:
			self.logger.warning('Attribute "value" is required for sampleRate element')
			return None

		try:
			value = float(value_str)
		except ValueError:
			self.logger.warning('Attribute "value" of sampleRate element is expected to be decimal')
			return None

		# Get optional 'uniform' attribute
		uniform_str = element.get('uniform')
		uniform = uniform_str is None or uniform_str == 'true'	 # default: true

		return Ink.SampleRate(value, uniform)

	def read_latency(self, element: Optional[Element]) -> Optional[Ink.Latency]:
		"""
		Read content of <latency> element.
		:param element: Element to be read
		"""
		if element is None:
			return None

		# Get required 'value' attribute
		value_str = element.get('value')
		if value_str is None:
			self.logger.warning('Attribute "value" is required for latency element')
			return None

		try:
			value = float(value_str)
		except ValueError:
			self.logger.warning('Attribute "value" of latency is expected to be decimal')
			return None

		return Ink.Latency(value)

	def read_active_area(self, element: Optional[Element]) -> Optional[Ink.ActiveArea]:
		"""
		Read content of <activeArea> element.
		:param element: Element to be read
		"""
		if element is None:
			return None

		# Get required 'width' attribute
		width_str = element.get('width')
		if width_str is None:
			self.logger.warning('Attribute "width" is required for activeArea element')
			return None

		try:
			width = float(width_str)
		except ValueError:
			self.logger.warning('Attribute "width" of activeArea is expected to be decimal')
			return None

		# Get required 'height' attribute
		height_str = element.get('height')
		if height_str is None:
			self.logger.warning('Attribute "height" is required for activeArea element')
			return None

		try:
			height = float(height_str)
		except ValueError:
			self.logger.warning('Attribute "height" of activeArea is expected to be decimal')
			return None

		active_area = Ink.ActiveArea(width, height)

		# Get optional 'size' attribute
		active_area.size = element.get('size')

		# Get optional 'units' attribute
		active_area.units = element.get('units')

		return active_area

	def read_source_property(self, element: Element) -> Optional[rt.SourceProperty]:
		"""
		Read content of <sourceProperty> element.
		:param element: Element to be read
		"""
		# Get required 'name' attribute
		name = element.get('name')
		if name is None:
			self.logger.warning('Attribute "name" is required for sourceProperty element')
			return None

		# Get required 'value' attribute
		value = element.get('value')
		if value is None:
			self.logger.warning('Attribute "value" is required for sourceProperty element')
			return None

		# Get optional 'units' attribute
		units = element.get('units')

		return rt.SourceProperty(name, value, units)

	def read_channel_property(self, element: Element) -> Optional[rt.ChannelProperty]:
		"""
		Read content of <channelProperty> element.
		:param element: Element to be read
		"""
		# Get required 'channel' attribute
		channel = element.get('channel')
		if channel is None:
			self.logger.warning('Attribute "channel" is required for channelProperty element')
			return None

		# Get required 'name' attribute
		name = element.get('name')
		if name is None:
			self.logger.warning('Attribute "name" is required for channelProperty element')
			return None

		# Get required 'value' attribute
		value = element.get('value')
		if value is None:
			self.logger.warning('Attribute "value" is required for channelProperty element')
			return None

		# Get optional 'units' attribute
		units = element.get('units')

		return rt.ChannelProperty(channel, name, value, units)

	def read_brush_property(self, element: Element) -> Optional[rt.BrushProperty]:
		"""
		Read content of <brushProperty> element.
		:param element: Element to be read
		"""
		# Get required 'name' attribute
		name = element.get('name')
		if name is None:
			self.logger.warning('Attribute "name" is required for brushProperty element')
			return None

		# Get required 'value' attribute
		value = element.get('value')
		if value is None:
			self.logger.warning('Attribute "value" is required for brushProperty element')
			return None

		# Get optional 'units' attribute
		units = element.get('units')

		brush_property = rt.BrushProperty(name, value, units)

		# Read annotations
		brush_property.annotations = self.read_annotations(element)

		return brush_property

	def read_annotations(self, container: Element) -> List[Ink.Annotation]:
		annotations: List[Ink.Annotation] = []
		for item in container:
			if item.tag == inkml.ANNOTATION or item.tag == inkml.ANNOTATION_XML:
				annotation = self.read_annotation(item)
				if annotation is not None:
					annotations.append(annotation)

		return annotations

	def read_annotation(self, element: Element) -> Optional[Ink.Annotation]:
		"""
		Read content of <annotation> or <annotationXML> element.
		:param element: Element to be read
		"""
		annotation: Ink.Annotation
		if element.tag == inkml.ANNOTATION:
			annotation = Ink.Annotation(element.text or '', Ink.AnnotationContentType.Text)
		elif element.tag == inkml.ANNOTATION_XML:
			inner_text = Reader.get_inner_text(element)
			if len(inner_text) > 0:
				annotation = Ink.Annotation(inner_text, Ink.AnnotationContentType.XML)
			else:
				href = element.get('href')
				if href is not None:
					annotation = Ink.Annotation(href, Ink.AnnotationContentType.HRef)
				else:
					self.logger.warning('Neither content, nor href is provided for annotationXML element')
					return None
		else:
			raise Exception('Unexpected annotation element: {}'.format(element.tag))

		# Get optional type attribute
		type = element.get('type')
		if type is not None:
			annotation.type = type

		# Get optional encoding attribute
		encoding = element.get('encoding')
		if encoding is not None:
			annotation.encoding = encoding

		# Store non-standard attributes
		for name, value in element.items():
			# Skip standard attributes
			if name == 'href' or name == 'type' or name == 'encoding':
				continue

			if value is not None:
				annotation.attributes[name] = value

		return annotation

	@staticmethod
	def get_inner_text(element):
		return (element.text or '') + ''.join(Reader.get_inner_text(e) for e in element) + (element.tail or '')

	def read_traces(self, container: Element,
	                definitions: rt.Definitions,
	                context: Optional[Ink.Context]) -> List[Ink.TraceItem]:
		traces: List[Ink.TraceItem] = []

		for child in container:
			if child.tag == inkml.TRACE:
				trace = self.read_trace(child, definitions, context)
				if trace is None:
					self.logger.warning('Could not read trace')
					continue

				traces.append(trace)

				if len(trace.id) > 0:
					definitions.traces[trace.id] = trace
			elif child.tag == inkml.TRACE_GROUP:
				group = self.read_trace_group(child, definitions)
				if group is None:
					self.logger.warning('Could not read traceGroup')
					continue

				group.traces = self.read_traces(child, definitions, group.context or context)

				traces.append(group)

				if len(group.id) > 0:
					definitions.trace_groups[group.id] = group
			elif child.tag == inkml.TRACE_VIEW:
				view = self.read_trace_view(child, definitions)
				if view is None:
					self.logger.warning('Could not read traceView')
					continue

				traces.append(view)

				if len(view.id) > 0:
					definitions.trace_views[view.id] = view

		return traces

	def read_trace_group(self, element: Element,
						 definitions: rt.Definitions,
						 require_refs: bool = True) -> Optional[Ink.TraceGroup]:
		"""
		Read content of <traceGroup> element.
		:param element: Element to be read
		:param definitions:
		:param require_refs:
		:return:
		"""
		trace_group = Ink.TraceGroup()

		# Get optional contextRef attribute
		context_ref = element.get('contextRef')
		if context_ref is not None:
			if is_local_id(context_ref) or self.assume_local_refs:
				context_id = to_local_id(context_ref)
				if context_id in definitions.contexts:
					trace_group.context = definitions.contexts[context_id].context
				else:
					self.logger.warning('Could not find context "{}" referenced by a traceGroup'.format(context_ref))
					if require_refs:
						return None
			else:
				self.logger.warning('External references are not yet supported: "{}"'.format(context_ref))

		# Get optional brushRef attribute
		brush_ref = element.get('brushRef')
		if brush_ref is not None:
			if is_local_id(brush_ref) or self.assume_local_refs:
				brush_id = to_local_id(brush_ref)
				if brush_id in definitions.brushes:
					trace_group.brush = definitions.brushes[brush_id].brush
				else:
					self.logger.warning('Could not find brush "{}" referenced by a traceGroup'.format(brush_ref))
					if require_refs:
						return None
			else:
				self.logger.warning('External references are not yet supported: "{}"'.format(brush_ref))

		# Get optional ID attribute
		id = self.get_id(element)
		if id is not None and len(id) > 0:
			trace_group.id = id

		# Read annotations
		trace_group.annotations = self.read_annotations(element)

		return trace_group

	def read_trace_view(self, element: Element, definitions: rt.Definitions) -> Optional[Ink.TraceView]:
		"""
		Read content of <traceView> element.
		:param element: Element to be read
		:param definitions:
		:return:
		"""
		# Get required 'traceDataRef' attribute
		trace_data_ref = element.get('traceDataRef')
		if trace_data_ref is None:
			self.logger.warning('Attribute "traceDataRef" is required for traceView element')
			return None

		if not is_local_id(trace_data_ref) and not self.assume_local_refs:
			self.logger.warning('External references are not yet supported: "{}"'.format(trace_data_ref))
			return None

		trace_data_id = to_local_id(trace_data_ref)

		# Look for referenced data
		# traceData: Ink.Trace | Ink.TraceGroup | Ink.TraceView
		if trace_data_id in definitions.traces:
			trace_data = definitions.traces[trace_data_id]
		elif trace_data_id in definitions.trace_groups:
			trace_data = definitions.trace_groups[trace_data_id]
		elif trace_data_id in definitions.trace_views:
			trace_data = definitions.trace_views[trace_data_id]
		else:
			self.logger.warning('Could not find trace data "{}" referenced by a traceView'.format(trace_data_ref))
			return None

		trace_view = Ink.TraceView(trace_data)

		# Get optional ID attribute
		id = self.get_id(element)
		if id is not None and len(id) > 0:
			trace_view.ID = id

		# Get optional 'from' attribute
		begin_str = element.get('from')
		if begin_str is not None and len(begin_str) > 0:
			try:
				trace_view.begin = [int(v) for v in begin_str.split(':')]
			except ValueError:
				self.logger.warning('Could not convert "from" values to integers: {}'.format(begin_str))
				trace_view.begin = []

		# Get optional 'to' attribute
		end_str = element.get('to')
		if end_str is not None and len(end_str) > 0:
			try:
				trace_view.end = [int(v) for v in end_str.split(':')]
			except ValueError:
				self.logger.warning('Could not convert "to" values to integers: {}'.format(end_str))
				trace_view.end = []

		return trace_view

	def read_trace(self,
	               element: Element,
	               definitions: rt.Definitions,
	               context: Optional[Ink.Context],
	               require_refs: bool = True) -> Optional[Ink.Trace]:
		"""
		Read content of <trace> element.
		:param element: Element to be read
		:param definitions:
		:param context:
		:param require_refs:
		:return:
		"""
		trace = Ink.Trace()

		# Get optional contextRef attribute
		context_ref = element.get('contextRef')
		if context_ref is not None:
			if is_local_id(context_ref) or self.assume_local_refs:
				context_id = to_local_id(context_ref)
				if context_id in definitions.contexts:
					trace.context = definitions.contexts[context_id].context
				else:
					self.logger.warning('Could not find context "{}" referenced by a trace'.format(context_ref))
					if require_refs:
						return None
			else:
				self.logger.warning('External references are not yet supported: "{}"'.format(context_ref))

		# Get optional brushRef attribute
		brush_ref = element.get('brushRef')
		if brush_ref is not None:
			if is_local_id(brush_ref) or self.assume_local_refs:
				brush_id = to_local_id(brush_ref)
				if brush_id in definitions.brushes:
					trace.brush = definitions.brushes[brush_id].brush
				else:
					self.logger.warning('Could not find brush "{}" referenced by a trace'.format(brush_ref))
					if require_refs:
						return None
			else:
				self.logger.warning('External references are not yet supported: "{}"'.format(brush_ref))

		# Get optional continuation attribute
		continuation = element.get('continuation')
		if continuation is not None:
			if continuation == 'begin':
				trace.continuation = Ink.TraceContinuation.Begin
			elif continuation == 'middle':
				trace.continuation = Ink.TraceContinuation.Middle
			elif continuation == 'end':
				trace.continuation = Ink.TraceContinuation.End
			else:
				self.logger.warning('Unexpected value of continuation attribute: "{}"'.format(continuation))

		# If this trace is a continuation, assign it to its prior trace
		if trace.continuation == Ink.TraceContinuation.Middle or trace.continuation == Ink.TraceContinuation.End:
			# Get required priorRef attribute
			prior_ref = element.get('priorRef')
			if prior_ref is None or len(prior_ref) == 0:
				self.logger.warning('Attribute priorRef is required because continuation is set to "{}"'.format(continuation))
				return None
			elif not is_local_id(prior_ref) and not self.assume_local_refs:
				self.logger.warning('External references are not yet supported: "{}"'.format(prior_ref))
				return None

			# Look for prior trace
			prior_id = to_local_id(prior_ref)
			if prior_id in definitions.traces:
				prior_trace = definitions.traces[prior_id]
				prior_trace.next = trace
			else:
				self.logger.warning('Could not find prior trace "{}" referenced by a trace'.format(prior_ref))
				if require_refs:
					return None

		# Parse trace data
		if element.text is not None:
			trace_format = self.get_trace_format(trace, context)
			regular_channels, intermittent_channels = self.parse_trace_content(element.text, trace_format)
			if regular_channels is None or intermittent_channels is None:
				self.logger.warning('Could not parse trace content')
				return None

			# Move data into trace
			for ch in regular_channels:
				trace.channels[ch.name] = ch.values
			for ch in intermittent_channels:
				trace.intermittent_channels[ch.name] = ch.index_values

		# Get ID attribute
		id = self.get_id(element)
		if id is not None and len(id) > 0:
			trace.id = id
		elif trace.continuation == Ink.TraceContinuation.Begin or trace.continuation == Ink.TraceContinuation.Middle:
			self.logger.warning('Continuation is set to "{}" but xml:id is missing'.format(continuation))

		# Get optional type attribute
		trace_type = element.get('type')
		if trace_type == 'penDown':
			trace.type = Ink.TraceType.PenDown
		elif trace_type == 'penUp':
			trace.type = Ink.TraceType.PenUp
		elif trace_type == 'indeterminate':
			trace.type = Ink.TraceType.Indeterminate

		# Get optional duration attribute
		duration_str = element.get('duration')
		if duration_str is not None and len(duration_str) > 0:
			try:
				trace.duration = int(duration_str)
			except ValueError:
				pass

		# Get optional timeOffset attribute
		time_offset_str = element.get('timeOffset')
		if time_offset_str is not None and len(time_offset_str) > 0:
			try:
				trace.time_offset = int(time_offset_str)
			except ValueError:
				pass

		return trace

	def parse_trace_content(self, content: str, trace_format: Ink.TraceFormat) \
			-> Tuple[Optional[List[rt.RegularChannel]], Optional[List[rt.IntermittentChannel]]]:
		# Wrap channels
		regular_channels = [rt.RegularChannel(ch.name, ch.type) for ch in trace_format.regular_channels]
		intermittent_channels = [rt.IntermittentChannel(ch.name, ch.type) for ch in trace_format.intermittent_channels]

		num_regular_channels = len(regular_channels)
		num_channels = num_regular_channels + len(trace_format.intermittent_channels)

		points = content.split(",")

		# Parse each point into channels
		for i, point in enumerate(points):
			point = point.strip()

			# Split raw point string into tokens
			tokens = [m[0] for m in self.tokenize_expr.findall(point)]

			# Check amount of tokens
			if len(tokens) < num_regular_channels or len(tokens) > num_channels:
				self.logger.warning('Expected between {} and {} values for a point, but got {}: {}'
				      .format(num_regular_channels, num_channels, len(tokens), point))
				return None, None

			# Process regular channels
			for j in range(num_regular_channels):
				token = tokens[j]
				channel = regular_channels[j]

				# Handle wildcard and go to next channel
				if token == '*':
					if len(channel.values) > 0:
						channel.values.append(channel.values[-1])
					else:
						self.logger.warning('Unexpected value "{}" in channel № {} (regular)'.format(token, j))
						return None, None

					continue

				# Handle boolean channel and go to next one
				if channel.type == Ink.ChannelType.Boolean:
					if token == 'T':
						channel.values.append(1)
					elif token == 'F':
						channel.values.append(0)
					else:
						self.logger.warning('Unexpected value "{}" in channel № {} (regular)'.format(token, j))
						return None, None

					continue

				# Get difference order
				difference_order = channel.difference_order
				if token[0] == '!':
					difference_order = rt.DifferenceOrder.Explicit
					token = token[1:]
				elif token[0] == "'":
					difference_order = rt.DifferenceOrder.Difference
					token = token[1:]
				elif token[0] == '"':
					difference_order = rt.DifferenceOrder.SecondDifference
					token = token[1:]

				# Remove any leading white spaces
				token = token.strip()

				# Check if there is minus sign
				is_negative = False
				if token[0] == '-':
					is_negative = True
					token = token[1:].strip()

				# Parse number
				try:
					num = int(token[1:], 16) if (token[0] == '#') else float(token)
				except ValueError:
					self.logger.warning('Unexpected value "{}" in channel № {} (regular)'.format(token, j))
					return None, None

				if is_negative:
					num *= -1

				# Add new value to the channel
				if difference_order == rt.DifferenceOrder.Explicit:
					value = num
					if channel.type == Ink.ChannelType.Integer:
						value = round(value)

					channel.values.append(value)
					channel.last_difference = float('nan')
				elif difference_order == rt.DifferenceOrder.Difference:
					if len(channel.values) == 0:
						self.logger.warning('Unexpected value "{}" in channel № {} (regular)'.format(token, j))
						return None, None

					value = channel.values[-1] + num
					if channel.type == Ink.ChannelType.Integer:
						value = round(value)

					channel.values.append(value)
					channel.last_difference = num
				elif difference_order == rt.DifferenceOrder.SecondDifference:
					if math.isnan(channel.last_difference):
						self.logger.warning('Unexpected value "{}" in channel № {} (regular)'.format(token, j))
						return None, None

					value = channel.values[-1] + channel.last_difference + num
					if channel.type == Ink.ChannelType.Integer:
						value = round(value)

					channel.values.append(value)
					channel.last_difference += num

				# Keep track of last difference order
				channel.difference_order = difference_order

			# Process intermittent channels
			for j in range(num_regular_channels, num_channels):
				token = tokens[j]
				channel = intermittent_channels[j - num_regular_channels]

				# Skip channel in case of placeholder
				if token == '?':
					continue

				# Handle wildcard and go to next channel
				if token == '*':
					if len(channel.index_values) > 0:
						channel.index_values.append(Ink.IndexValue(i, channel.index_values[-1].value))
					else:
						self.logger.warning('Unexpected value "{}" in channel № ${} (intermittent)'.format(token, j))
						return None, None

					continue

				if channel.type == Ink.ChannelType.Boolean:
					# Handle boolean channel
					if token == 'T':
						channel.index_values.append(Ink.IndexValue(i, 1))
					elif token == 'F':
						channel.index_values.append(Ink.IndexValue(i, 0))
					else:
						self.logger.warning('Unexpected value "{}" in channel № ${} (intermittent)'.format(token, j))
						return None, None
				else:
					# Check if there is minus sign
					is_negative = False
					if token[0] == '-':
						is_negative = True
						token = token[1:].strip()

					# Parse number
					try:
						value = int(token[1:], 16) if (token[0] == '#') else float(token)
					except ValueError:
						self.logger.warning('Unexpected value "{}" in channel № {} (intermittent)'.format(token, j))
						return None, None

					if is_negative:
						value *= -1

					if channel.type == Ink.ChannelType.Integer:
						value = round(value)

					# Add new value to the channel
					channel.index_values.append(Ink.IndexValue(i, value))

		return regular_channels, intermittent_channels

	@staticmethod
	def get_id(element: Element) -> Optional[str]:
		"""Get id attribute.
		According to the standard we should be looking for 'id' attribute in 'xml' namespace,
		however, some writers seem to ignore the namespace.

		Args:
			element: An XML element

		Returns:
			String or None
		"""
		id = element.get(inkml.ID)
		if id is None:
			id = element.get('id')
		return id

	@staticmethod
	def get_trace_format(trace: Ink.Trace, external_context: Optional[Ink.Context]) -> Ink.TraceFormat:
		context = trace.context or external_context
		if context is None:
			return Ink.get_default_trace_format()

		# Try to get traceFormat directly from context (considering parent contexts)
		ctx = context
		while ctx is not None:
			if ctx.trace_format is not None:
				return ctx.trace_format

			ctx = ctx.parent

		# Try to get traceFormat from inkSource (considering parent contexts)
		ctx = context
		while ctx is not None:
			if ctx.ink_source is not None:
				return ctx.ink_source.trace_format

			ctx = ctx.parent

		return Ink.get_default_trace_format()
