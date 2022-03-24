from typing import Optional


def is_local_id(uri: str) -> bool:
	return len(uri) > 1 and uri[0] == '#'


def to_local_id(uri: str) -> str:
	return uri[1:] if is_local_id(uri) else uri


def to_optional_local_id(uri: str) -> Optional[str]:
	return uri[1:] if is_local_id(uri) else None
