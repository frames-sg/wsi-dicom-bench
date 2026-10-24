"""Shared constants for mutations that inspect encoded DICOM files."""

from pydicom.valuerep import EXPLICIT_VR_LENGTH_32


PREAMBLE_AND_PREFIX = 132
LONG_LENGTH_VRS = frozenset(vr.encode("ascii") for vr in EXPLICIT_VR_LENGTH_32)
