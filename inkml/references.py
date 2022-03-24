from typing import Mapping, Set
from . import ink, reading_types as rt
from .ids import is_local_id, to_local_id


def resolve_references(definitions: rt.Definitions, assume_local_refs):
	# Resolve Brush.parentRef
	ignored_ids = resolve_brush_parent_references(definitions.brushes)

	if len(ignored_ids) > 0:
		for id in ignored_ids:
			del definitions.brushes[id]

		print('Some brush references are either cyclic or incorrect and could not be resolved.Following brushes will '
		      'be ignored: {} '.format(', '.join(ignored_ids)))

	# Resolve Timestamp.parentRef
	ignored_ids = resolve_timestamp_parent_references(definitions.timestamps)

	if len(ignored_ids) > 0:
		for id in ignored_ids:
			del definitions.timestamps[id]

		print('Some timestamp references are either cyclic or incorrect and could not be resolved.Following timestamps '
		      'will be ignored: {} '.format(', '.join(ignored_ids)))

	# Resolve Context.parentRef
	ignored_ids = resolve_context_parent_references(definitions.contexts)

	if len(ignored_ids) > 0:
		for id in ignored_ids:
			del definitions.contexts[id]

		print('Some context references are either cyclic or incorrect and could not be resolved.Following timestamps '
		      'will be ignored: {} '.format(', '.join(ignored_ids)))

	# Resolve Context.inkSourceRef, Context.traceFormatRef, Context.brushRef and Context.inkSourceRef
	resolve_context_content_references(definitions, assume_local_refs)


def resolve_brush_parent_references(brushes: Mapping[str, rt.BrushEnvelope]) -> Set[str]:
	backlog: Set[str] = set()
	resolved: Set[str] = set()

	# Find all terminal brushes that do not reference other brushes
	for brush in brushes.values():
		if brush.parent_ref == '' or brush.parent_ref == '#DefaultBrush':
			resolved.add(brush.id)
		else:
			backlog.add(brush.id)

	while len(backlog) > 0:
		# Look for brushes that reference already resolved brushes (and thus can be resolved)
		stage_ids = []
		for id in backlog:
			brush = brushes[id]
			parent_id = to_local_id(brush.parent_ref)
			if parent_id in resolved:
				# Resolve reference
				brush.brush.parent = brushes[parent_id].brush

				stage_ids.append(id)

		# Stop, if no refs were resolved at this stage
		if len(stage_ids) == 0:
			break

		# Mark brushes resolved at this stage and remove them from backlog
		for id in stage_ids:
			resolved.add(id)
			backlog.remove(id)

	# TODO: replace missing ref by no-ref and keep the item itself? (only drop cycles)

	# NOTE: if backlog is not empty at this point, there are cyclic or incorrect references
	return backlog


def resolve_timestamp_parent_references(timestamps: Mapping[str, rt.TimestampEnvelope]) -> Set[str]:
	backlog: Set[str] = set()
	resolved: Set[str] = set()

	# Find all terminal timestamps that do not reference other timestamps
	for timestamp in timestamps.values():
		if timestamp.parent_ref == '':
			resolved.add(timestamp.id)
		else:
			backlog.add(timestamp.id)

	while len(backlog) > 0:
		# Look for timestamps that reference already resolved timestamps (and thus can be resolved)
		stage_ids = []
		for id in backlog:
			timestamp = timestamps[id]
			parent_id = to_local_id(timestamp.parent_ref)
			if parent_id in resolved:
				# Resolve reference
				timestamp.timestamp.parent = timestamps[parent_id].timestamp

				stage_ids.append(id)

		# Stop, if no refs were resolved at this stage
		if len(stage_ids) == 0:
			break

		# Mark timestamps resolved at this stage and remove them from backlog
		for id in stage_ids:
			resolved.add(id)
			backlog.remove(id)

	# NOTE: if backlog is not empty at this point, there are cyclic or incorrect references
	return backlog


def resolve_context_parent_references(contexts: Mapping[str, rt.ContextEnvelope]) -> Set[str]:
	backlog: Set[str] = set()
	resolved: Set[str] = set()

	# Find all terminal contexts that do not reference other contexts
	for context in contexts.values():
		if context.parent_ref == '':
			resolved.add(context.id)
		else:
			backlog.add(context.id)

	while len(backlog) > 0:
		# Look for contexts that reference already resolved contexts (and thus can be resolved)
		stage_ids = []
		for id in backlog:
			context = contexts[id]
			parent_id = to_local_id(context.parent_ref)
			if parent_id in resolved:
				# Resolve reference
				context.context.parent = contexts[parent_id].context

				stage_ids.append(id)

		# Stop, if no refs were resolved at this stage
		if len(stage_ids) == 0:
			break

		# Mark contexts resolved at this stage and remove them from backlog
		for id in stage_ids:
			resolved.add(id)
			backlog.remove(id)

	# NOTE: if backlog is not empty at this point, there are cyclic or incorrect references
	return backlog


def resolve_context_content_references(definitions: rt.Definitions, assume_local_refs):
	for context in definitions.contexts.values():
		# Set Context.ink_source
		if isinstance(context.ink_source_or_ref, ink.InkSource):
			context.context.ink_source = context.ink_source_or_ref
		elif len(context.ink_source_or_ref) > 0:
			if is_local_id(context.ink_source_or_ref) or assume_local_refs:
				ink_source_id = to_local_id(context.ink_source_or_ref)
				if ink_source_id in definitions.ink_sources:
					context.context.ink_source = definitions.ink_sources[ink_source_id]
				else:
					print('Warning. Could not find inkSource "{}" referenced by context "{}"'
					      .format(context.ink_source_or_ref, context.id))
			else:
				print('Warning. External references are not yet supported: "{}"'.format(context.ink_source_or_ref))

		# Set Context.trace_format
		if isinstance(context.trace_format_or_ref, ink.TraceFormat):
			context.context.trace_format = context.trace_format_or_ref
		elif len(context.trace_format_or_ref) > 0:
			if is_local_id(context.trace_format_or_ref) or assume_local_refs:
				trace_format_id = to_local_id(context.trace_format_or_ref)
				if trace_format_id in definitions.trace_formats:
					context.context.trace_format = definitions.trace_formats[trace_format_id]
				else:
					print('Warning. Could not find traceFormat "{}" referenced by context "{}"'
					      .format(context.trace_format_or_ref, context.id))
			else:
				print('Warning. External references are not yet supported: "{}"'.format(context.trace_format_or_ref))

		# Set Context.brush
		if isinstance(context.brush_or_ref, rt.BrushEnvelope):
			# Set brush that is given as a nested element
			if len(context.brush_or_ref.id) > 0:
				# This brush has an ID, so its refs should already be resolved. Take it from definitions
				if context.brush_or_ref.id in definitions.brushes:
					context.context.brush = definitions.brushes[context.brush_or_ref.id].brush
				else:
					# This brush is not in definitions, which means that it was ignored for some reason
					print('Warning. Context "{}" references a brush that was ignored'.format(context.id))
			else:
				# This brush has no ID, so it is not in definitions
				context.context.brush = context.brush_or_ref.brush

				# If needed, resolve parent reference of this brush here, because it was not processed before
				if len(context.brush_or_ref.parent_ref) > 0:
					parent_id = to_local_id(context.brush_or_ref.parent_ref)
					if parent_id in definitions.brushes:
						context.context.brush.parent = definitions.brushes[parent_id].brush
					else:
						print('Warning. Could not find brush "{}" referenced by brush "{}"'
						      .format(context.brush_or_ref.parent_ref, context.brush_or_ref.id))
		elif len(context.brush_or_ref) > 0:
			if is_local_id(context.brush_or_ref) or assume_local_refs:
				# Set brush that is given as a reference
				brush_id = to_local_id(context.brush_or_ref)
				if brush_id in definitions.brushes:
					context.context.brush = definitions.brushes[brush_id].brush
				else:
					print('Warning. Could not find brush "{}" referenced by context "{}"'
					      .format(context.brush_or_ref, context.id))
			else:
				print('Warning. External references are not yet supported: "{}"'.format(context.brush_or_ref))

		# Set Context.timestamp
		if isinstance(context.timestamp_or_ref, rt.TimestampEnvelope):
			# Set timestamp that is given as a nested element
			if len(context.timestamp_or_ref.id) > 0:
				# This timestamp has an ID, so its refs should already be resolved. Take it from definitions
				if context.timestamp_or_ref.id in definitions.timestamps:
					context.context.timestamp = definitions.timestamps[context.timestamp_or_ref.id].timestamp
				else:
					# This timestamp is not in definitions, which means that it was ignored for some reason
					print('Context "{}" references a timestamp that was ignored'.format(context.id))
			else:
				# This timestamp has no ID, so it is not in definitions
				context.context.timestamp = context.timestamp_or_ref.timestamp

				# If needed, resolve parent reference of this timestamp here, because it was not processed before
				if len(context.timestamp_or_ref.parent_ref) > 0:
					if context.timestamp_or_ref.parent_ref in definitions.timestamps:
						context.context.timestamp.parent = \
							definitions.timestamps[context.timestamp_or_ref.parent_ref].timestamp
					else:
						print('Could not find timestamp "{}" referenced by timestamp "${}"'
						      .format(context.timestamp_or_ref.parent_ref, context.timestamp_or_ref.id))
		elif len(context.timestamp_or_ref) > 0:
			if is_local_id(context.timestamp_or_ref) or assume_local_refs:
				# Set timestamp that is given as a reference
				timestamp_id = to_local_id(context.timestamp_or_ref)
				if timestamp_id in definitions.timestamps:
					context.context.timestamp = definitions.timestamps[timestamp_id].timestamp
				else:
					print('Could not find timestamp "{}" referenced by context "{}"'
					      .format(context.timestamp_or_ref, context.id))
			else:
				print('External references are not yet supported: "{}"'.format(context.timestamp_or_ref))
