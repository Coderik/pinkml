from typing import Union, Optional, List, Dict, NewType
from enum import Enum


class Ink:
	def __init__(self):
		self.traces: List[TraceItem] = []
		self.annotations: List[Annotation] = []
		self.definitions = Definitions()


class Definitions:
	def __init__(self):
		self.contexts: List[Context] = []
		self.brushes: List[Brush] = []
		self.ink_sources: List[InkSource] = []
		self.trace_formats: List[TraceFormat] = []
		self.timestamps: List[Timestamp] = []


class Trace:
	def __init__(self):
		self.id: str = ''
		self.channels: Dict[str, List[float]] = dict()
		self.intermittent_channels: Dict[str, List[IndexValue]] = dict()
		self.continuation: TraceContinuation = TraceContinuation.No
		self.next: Optional[Trace] = None       # TODO: OR prev?
		self.context: Optional[Context] = None
		self.brush: Optional[Brush] = None
		self.duration: Optional[float] = None
		self.time_offset: Optional[float] = None
		self.type: TraceType = TraceType.PenDown


class TraceContinuation(Enum):
	Begin = 0
	Middle = 1
	End = 2
	No = 3


class IndexValue:
	def __init__(self, index: int, value: float):
		self.index = index
		self.value = value


class TraceGroup:
	def __init__(self):
		self.id: str = ''
		self.context: Optional[Context] = None
		self.brush: Optional[Brush] = None
		self.traces: List[TraceItem] = []
		self.annotations: List[Annotation] = []


class TraceType(Enum):
	PenDown = 'penDown',
	PenUp = 'penUp',
	Indeterminate = 'indeterminate'


class TraceView:
	def __init__(self, trace_data):
		self.id: str = ''
		self.trace_data: TraceItem = trace_data
		self.begin: List[int] = []
		self.end: List[int] = []


TraceItem = NewType('TraceItem', Union[Trace, TraceGroup, TraceView])


class IHeritable:
	def __init__(self, id: str, parent):
		self.id = id
		self.parent: Optional[IHeritable] = parent


class Accountable:
	_next_instance_index_ = 0

	def __init__(self):
		self.instance_index = Accountable._next_instance_index_
		Accountable._next_instance_index_ += 1

	def is_(self, other):
		return isinstance(other, Accountable) and other.instance_index == self.instance_index


class Context(IHeritable, Accountable):
	def __init__(self):
		super().__init__(id='', parent=None)

		self.ink_source: Optional[InkSource] = None
		self.trace_format: Optional[TraceFormat] = None
		self.brush: Optional[Brush] = None
		self.timestamp: Optional[Timestamp] = None


class Property:
	def __init__(self, value: Union[int, float, str], units: Optional[str] = None):
		self.value = value      # Value of named value
		self.units = units      # Units used for value


class AnnotationContentType(Enum):
	Text = 0
	XML = 1
	HRef = 2


class Annotation:
	def __init__(self, content: str, content_type: AnnotationContentType):
		self.content = content
		self.content_type = content_type
		self.type: str = ''
		self.encoding: str = ''
		self.attributes: Dict[str, str] = dict()


class AnnotatedProperty(Property):
	def __init__(self,
	             value: Union[int, float, str],
	             units: Optional[str] = None,
	             annotations: Optional[List[Annotation]] = None):
		super().__init__(value, units)

		self.annotations = annotations if annotations is not None else []


class TraceFormat(Accountable):
	def __init__(self):
		super().__init__()

		self.id: str = ''        # (optional) Unique identifier
		self.regular_channels: List[Channel] = []
		self.intermittent_channels: List[Channel] = []


class InkSource(Accountable):
	def __init__(self, id: str, trace_format: TraceFormat):
		super().__init__()

		self.id = id        # (required) Unique identifier
		self.trace_format = trace_format     # (required)
		self.sample_rate: Optional[SampleRate] = None
		self.latency: Optional[Latency] = None
		self.active_area: Optional[ActiveArea] = None
		self.manufacturer: Optional[str] = None
		self.model: Optional[str] = None
		self.serial_no: Optional[str] = None
		self.specification_ref: Optional[str] = None
		self.description: Optional[str] = None
		self.properties: Dict[str, Property] = dict()        # name -> value


class Channel:
	def __init__(self, name: str):
		self.id: str = ''   # (optional) Unique identifier
		self.name = name    # (required) Case sensitive name of this channel
		self.type: ChannelType = ChannelType.Decimal
		self.default: Union[float, bool] = 0
		self.min: Optional[float] = None
		self.max: Optional[float] = None
		self.orientation: ChannelOrientation = ChannelOrientation.Positive
		self.respect_to: str = ''
		self.units: str = ''
		self.properties: Dict[str, Property] = dict()        # name -> value
		# TODO: handle <mapping> elements


class ChannelType(Enum):
	Integer = 'integer'
	Decimal = 'decimal'
	Double = 'double'
	Boolean = 'boolean'


class ChannelOrientation(Enum):
	Positive = '+ve'
	Negative = '-ve'


class SampleRate:
	def __init__(self, value: float, uniform: bool = True):
		self.value = value          # The basic sample rate in samples/second
		self.uniform = uniform      # Sampling uniformity: Is the sample rate consistent, with no dropped points?


class Latency:
	def __init__(self, value: float):
		self.value = value          # Latency in milliseconds


class ActiveArea:
	def __init__(self, width: float, height: float):
		self.width = width
		self.height = height
		self.units: Optional[str] = None     # Units used for width and height
		self.size: Optional[str] = None      # The active area, described using an international ISO paper sizes standard such as ISO216


class Brush(IHeritable, Accountable):
	def __init__(self):
		super().__init__(id='', parent=None)

		self.properties: Dict[str, AnnotatedProperty] = dict()       # name -> value
		self.annotations: List[Annotation] = []


class Timestamp(IHeritable, Accountable):
	def __init__(self, id: str):
		super().__init__(id=id, parent=None)

		self.time: Optional[int] = None     # (optional) Absolute time for this parent, in milliseconds since 1 January 1970 00:00:00 UTC
		self.time_string: str = ''          # (optional) Absolute time for this parent, given in a human-readable standard format
		self.time_offset: int = 0           # (optional) Relative time for this reference parent, in milliseconds


def get_default_trace_format() -> TraceFormat:
	trace_format = TraceFormat()
	trace_format.id = 'DefaultTraceFormat'
	trace_format.regular_channels = [Channel('X'), Channel('Y')]
	return trace_format



