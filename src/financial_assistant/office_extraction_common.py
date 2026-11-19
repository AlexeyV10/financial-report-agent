"""Bounds and exact Office part reads shared by native extraction adapters."""

from zipfile import BadZipFile

from .safe_import import ImportValidationError, _archive_name, _read_member


MAX_CELLS = 3000
MAX_TEXT = 4096


class ExtractionError(ValueError):
    """Stable error code without an original filename or extracted text."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def xml_part(archive, name, *, optional=False):
    try:
        info = archive.getinfo(name)
    except KeyError:
        if optional:
            return None
        raise ExtractionError('office_part_missing') from None
    try:
        original, _ = _archive_name(info)
        if original != name or info.is_dir():
            raise ExtractionError('office_part_invalid')
        return _read_member(archive, info, True)
    except ImportValidationError as error:
        raise ExtractionError(error.code) from None
    except (BadZipFile, OSError, EOFError, RuntimeError):
        raise ExtractionError('office_part_invalid') from None
