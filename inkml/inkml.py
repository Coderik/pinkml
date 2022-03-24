"""
Some tags and attributes within the inkml namespace
"""

# Namespaces
INKML_NAMESPACE_URI = 'http://www.w3.org/2003/InkML'
XML_NAMESPACE_URI = 'http://www.w3.org/XML/1998/namespace'

# Tags
INK = '{{{}}}ink'.format(INKML_NAMESPACE_URI)
ANNOTATION = '{{{}}}annotation'.format(INKML_NAMESPACE_URI)
ANNOTATION_XML = '{{{}}}annotationXML'.format(INKML_NAMESPACE_URI)
TRACE = '{{{}}}trace'.format(INKML_NAMESPACE_URI)
TRACE_GROUP = '{{{}}}traceGroup'.format(INKML_NAMESPACE_URI)
TRACE_VIEW = '{{{}}}traceView'.format(INKML_NAMESPACE_URI)

# Attributes
ID = '{{{}}}id'.format(XML_NAMESPACE_URI)
