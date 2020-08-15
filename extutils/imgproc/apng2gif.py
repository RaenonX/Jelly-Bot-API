"""
Module to convert ``apng`` to ``gif``.
"""
import io
from dataclasses import dataclass, field
from fractions import Fraction
import os
import shutil
from tempfile import TemporaryDirectory
import time
from typing import Any, Tuple, List, Optional
from zipfile import ZipFile

from PIL import Image

from .apng2png import extract_frames

__all__ = ["convert", "ConvertResult", "ConvertOpResult"]

_IDX_CLR_BACKGROUND = 255
_IDX_CLR_TRANSPARENT = 255


class ConvertOpResult:
    """
    Result of an operation during the conversion.
    """

    def __init__(self):
        self._success = False
        self._duration = 0.0
        self._exception = None
        self._locked = False

    def _check_lock(self):
        if self._locked:
            raise ValueError(f"The operation is completed. (success={self._success})")

    def set_success(self, duration: float):
        """
        Set the convert operation as success. Also set the operation execution duration.

        :param duration: duration of the operation
        """
        self._check_lock()

        self._success = True
        self._duration = duration
        self._locked = True

    def set_failure(self, exception: Optional[Exception] = None):
        """
        Set the convert operation as failed. Also set the exception raised if any.

        :param exception: exception raised causing the failure
        """
        self._check_lock()

        self._success = False
        self._exception = exception
        self._locked = True

    @property
    def success(self) -> bool:
        """
        Check if the operation succeed.

        :return: if the operation succeed
        """
        return self._success

    @property
    def duration(self) -> float:
        """
        Get the time spent on operation in seconds.

        :return: time spent on operation in seconds
        """
        return self._duration

    @property
    def exception(self) -> Optional[Exception]:
        """
        Get the raised exception (if any).

        :return: raised exception (if any)
        """
        return self._exception


@dataclass
class ConvertResult:
    """
    The result of the conversion.

    Unit of the duration is seconds.
    """
    input_exists: bool = True

    frame_extraction: ConvertOpResult = field(default_factory=ConvertOpResult)
    frame_zipping: ConvertOpResult = field(default_factory=ConvertOpResult)
    image_data_collation: ConvertOpResult = field(default_factory=ConvertOpResult)
    gif_merging: ConvertOpResult = field(default_factory=ConvertOpResult)

    @property
    def succeed(self) -> bool:
        """
        Check if the conversion succeed.

        :return: if the conversion succeed
        """
        if not self.input_exists or self.frame_extraction.exception:
            return False

        return self.frame_extraction.success and self.image_data_collation.success and self.gif_merging.success

    @property
    def time_spent(self):
        """
        Get the total time spent on converting the image.

        :return: conversion total time spent
        """
        return self.frame_extraction.duration \
               + self.frame_zipping.duration \
               + self.image_data_collation.duration \
               + self.gif_merging.duration  # noqa: E126,E127


def _get_file_name(file_path: str) -> str:
    """
    Get the file name without extension.

    :param file_path: path of the file
    :return: file name without extension
    """
    return os.path.splitext(os.path.basename(file_path))[0]


def _extract_frames(result: ConvertResult, file_path: str) -> Optional[List[Tuple[bytes, Fraction]]]:
    """
    Extract the frames of the APNG file at ``apng_path``
    and return it as a list of 2-tuple containing the image byte data and its delay.

    If the extraction failed, returns ``None``
    and record the exception to ``result.frame_extraction_exception`` instead.

    :param result: conversion result object
    :param file_path: file path of the apng file to be extracted
    """
    _start = time.time()

    try:
        ret = extract_frames(file_path)
    except Exception as ex:
        result.frame_extraction.set_failure(ex)
        return None

    result.frame_extraction.set_success(time.time() - _start)

    return ret


def _zip_frames(result: ConvertResult, apng_path: str, frame_data: List[Tuple[bytes, Fraction]], output_path: str):
    """
    Zip the frames to be a single zip file preceded with the apng file name.

    :param result: conversion result object
    :param apng_path: path of the source apng
    :param frame_data: list of 2-tuple containing the image byte data and its delay
    :param output_path: output directory of the zip file
    """
    _start = time.time()

    apng_name = _get_file_name(apng_path)
    out_name = _get_file_name(output_path)

    try:
        with ZipFile(os.path.join(os.path.dirname(output_path), f"{out_name}-frames.zip"), "w") as zip_file:
            for idx, data in enumerate(frame_data, start=1):
                frame, _ = data
                zip_file.writestr(f"{apng_name}-{idx:02d}.png", frame)
    except Exception as ex:
        result.frame_zipping.set_failure(ex)
        return

    result.frame_zipping.set_success(time.time() - _start)


def _process_frame_transparent(image_byte: bytes):
    """
    Apply color index for transparency ``transparent_index`` to ``image_byte``
    and return the modified PIL image object.

    Copied and modified from ``apng2gif``.

    :param image_byte: byte data of an image/frame
    """
    image = Image.open(io.BytesIO(image_byte))
    alpha = image.getchannel("A")
    # Convert the image into P mode but only use 255 colors in the palette out of 256
    image = image.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=255)
    # Set all alpha < 128 to value 255, 0 otherwise
    image.paste(_IDX_CLR_TRANSPARENT, Image.eval(alpha, lambda a: 255 if a <= 128 else 0))
    return image


def _get_image_data(result: ConvertResult, frame_data: List[Tuple[bytes, Fraction]]) \
        -> Tuple[List[Any], List[Fraction]]:
    """
    Collate and process the data of ``frame_data``.

    Returns a 2-tuple which:
    - 1st element is the processed frames in PIL image objects
    - 2nd element is the duration of each frames

    :param result: conversion result object
    :param frame_data: list of 2-tuple containing frame byte data and its delay
    :return: frame data to be used to compose a gif
    """
    _start = time.time()

    images = []
    durations = []

    try:
        for image_byte, delay in frame_data:
            images.append(_process_frame_transparent(image_byte))
            durations.append(delay)
    except Exception as ex:
        result.image_data_collation.set_failure(ex)
        return [], []

    result.image_data_collation.set_success(time.time() - _start)

    return images, durations


def _make_gif(result: ConvertResult, frame_data: List[Tuple[bytes, Fraction]], output_path: str):
    """
    Use the extracted ``frame_data`` to construct a gif and output it to ``output_path``.

    :param result: conversion result object
    :param frame_data: list of 2-tuple containing frame byte data and its delay
    :param output_path: path for the completed gif
    """
    images, durations = _get_image_data(result, frame_data)

    if not result.image_data_collation.success:
        return

    _start = time.time()

    image, *images = images  # Take out the first image as the base image

    try:
        image.save(output_path, format="GIF", save_all=True, append_images=images, loop=0, disposal=2,
                   transparency=_IDX_CLR_TRANSPARENT, background=_IDX_CLR_BACKGROUND,
                   optimize=True, duration=durations)
    except Exception as ex:
        result.gif_merging.set_failure(ex)
        return

    result.gif_merging.set_success(time.time() - _start)


def convert(apng_path: str, output_path: str, *, zip_frames: bool = True) -> ConvertResult:
    """
    Convert the file at ``apng_path`` to gif and store it at ``output_path``.

    :param apng_path: path of the apng to be converted
    :param output_path: path for the processed gif
    :param zip_frames: to zip the extracted frames
    :return: result of the conversion
    """
    original_dir = os.getcwd()
    result = ConvertResult()

    if not os.path.exists(apng_path):
        result.input_exists = False
        return result

    with TemporaryDirectory() as temp_dir:
        # Copy the image for extraction
        apng_path_dst = os.path.join(temp_dir, os.path.basename(apng_path))

        shutil.copy(apng_path, apng_path_dst)
        apng_path = apng_path_dst

        # Set the current working directory to the temp directory
        os.chdir(temp_dir)

        # Main process
        out_path = output_path if os.path.isabs(output_path) else os.path.join(original_dir, output_path)

        frame_data = _extract_frames(result, apng_path)
        if result.frame_extraction.success:
            if zip_frames:
                _zip_frames(result, apng_path, frame_data, out_path)

            _make_gif(result, frame_data, out_path)

        # Restore the working directory (REQUIRED, disabling this causes infinite recursion)
        os.chdir(original_dir)

        return result
