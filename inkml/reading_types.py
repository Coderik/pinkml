from typing import Union, Optional, List, Dict
from enum import Enum
from . import ink


class Definitions:
	def __init__(self):
		self.contexts:          Dict[str, ContextEnvelope] = dict()
		self.brushes:           Dict[str, BrushEnvelope] = dict()
		self.ink_sources:       Dict[str, ink.InkSource] = dict()
		self.trace_formats:     Dict[str, ink.TraceFormat] = dict()
		self.timestamps:        Dict[str, TimestampEnvelope] = dict()
		self.traces:            Dict[str, ink.Trace] = dict()
		self.trace_groups:      Dict[str, ink.TraceGroup] = dict()
		self.trace_views:       Dict[str, ink.TraceView] = dict()


class ContextEnvelope:
	def __init__(self):
		self.context = ink.Context()
		self.parent_ref: str = ''
		self.ink_source_or_ref: Union[ink.InkSource, str] = ''
		self.trace_format_or_ref: Union[ink.TraceFormat, str] = ''
		self.brush_or_ref: Union[BrushEnvelope, str] = ''
		self.timestamp_or_ref: Union[TimestampEnvelope, str] = ''

	@property
	def id(self):
		return self.context.id


class BrushEnvelope:
	def __init__(self):
		self.brush = ink.Brush()
		self.parent_ref: str = ''

	@property
	def id(self):
		return self.brush.id


class TimestampEnvelope:
	def __init__(self, timestamp_id: str):
		self.timestamp = ink.Timestamp(timestamp_id)
		self.parent_ref: str = ''  # (optional) Another parent relative to which this parent is specified

	@property
	def id(self):
		return self.timestamp.id


class RegularChannel:
	def __init__(self, name: str, channel_type: ink.ChannelType):
		self.name = name
		self.type = channel_type
		self.values: List[float] = []
		self.difference_order: DifferenceOrder = DifferenceOrder.Explicit
		self.last_difference: float = float('nan')


class DifferenceOrder(Enum):
	Explicit = 0
	Difference = 1
	SecondDifference = 2


class IntermittentChannel:
	def __init__(self, name: str, channel_type: ink.ChannelType):
		self.name = name
		self.type = channel_type
		self.index_values: List[ink.IndexValue] = []


class ChannelProperty:
	"""
	Content of <channelProperty> tag stored as-is. Is used only while reading
	"""
	def __init__(self, channel: str, name: str, value: Union[float, str], units: Optional[str] = None):
		self.channel = channel      # Must be one among those defined by the ink source's trace format
		self.name = name            # Name of the value of channel
		self.value = value          # Value of named value
		self.units = units          # Units used for value


class SourceProperty:
	"""
	Content of <sourceProperty> tag stored as-is. Is used only while reading
	"""
	def __init__(self, name: str, value: Union[float, str], units: Optional[str] = None):
		self.name = name        # Name of the value of device or ink source
		self.value = value      # Value of named value
		self.units = units      # Units used for value


class BrushProperty:
	"""
	Content of <brushProperty> tag stored as-is. Is used only while reading
	"""
	def __init__(self, name: str, value: Union[float, str], units: Optional[str] = None):
		self.name = name        # (required) Name of value
		self.value = value      # (required) Value of named value
		self.units = units      # (optional) Units used for value
		self.annotations: List[ink.Annotation] = []
