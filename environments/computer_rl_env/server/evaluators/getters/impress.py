import logging
import os
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict

from .file import get_vm_file

logger = logging.getLogger(__name__)


def get_background_image_in_slide(env: Any, config: Dict[str, str]):
    ppt_file_path = config.get("ppt_file_path")
    slide_index = int(config.get("slide_index", 0))
    dest = config.get("dest")

    image_id = None
    image_file_path = None

    # Download ppt config file first
    ppt_file_filename = os.path.basename(ppt_file_path)
    ppt_file_localhost_path = get_vm_file(env, {"path": ppt_file_path, "dest": ppt_file_filename})

    if not ppt_file_localhost_path or not os.path.exists(ppt_file_localhost_path):
        return None

    try:
        with zipfile.ZipFile(ppt_file_localhost_path, "r") as myzip:
            slide1_xml_file = "ppt/slides/slide{}.xml".format(slide_index + 1)
            if slide1_xml_file not in myzip.namelist():
                return None

            with myzip.open(slide1_xml_file) as f:
                tree = ET.parse(f)
                root = tree.getroot()
                bg_tag = "{http://schemas.openxmlformats.org/presentationml/2006/main}bgPr"
                image_tag = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
                attr_tag = (
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
                )
                for child in root.iter(bg_tag):
                    try:
                        for element in child.iter(image_tag):
                            image_id = element.attrib[attr_tag]
                            break
                    except Exception as e:
                        logger.error(f"Error processing pptx: {e}")
                        pass
                    if image_id is not None:
                        break
                else:
                    return None

            # next, extract the background image
            slide1_rels_file = "ppt/slides/_rels/slide{}.xml.rels".format(slide_index + 1)
            if slide1_rels_file in myzip.namelist():
                with myzip.open(slide1_rels_file) as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    namespaces = {
                        "r": "http://schemas.openxmlformats.org/package/2006/relationships"
                    }
                    for rel in root.findall("r:Relationship", namespaces):
                        if "image" in rel.attrib["Type"] and rel.attrib["Id"] == image_id:
                            target = rel.attrib["Target"]
                            if target.startswith(".."):
                                image_file_path = os.path.normpath(
                                    os.path.join("ppt/slides", target)
                                )
                                image_file_path = image_file_path.replace("\\", "/")
                                tmpdirname = os.path.dirname(ppt_file_localhost_path)
                                myzip.extract(image_file_path, tmpdirname)
                                image_file_path = os.path.join(tmpdirname, image_file_path)
                                return image_file_path
                            else:
                                if target.startswith("file://"):
                                    image_file_path = target[7:]
                                else:
                                    image_file_path = target
                            break
    except Exception as e:
        logger.error(f"Error processing pptx: {e}")
        return None

    if image_file_path is None:
        return None
    else:
        # Get the file from vm
        return get_vm_file(env, {"path": image_file_path, "dest": dest})


def get_audio_in_slide(env: Any, config: Dict[str, str]):
    ppt_file_path = config.get("ppt_file_path")
    slide_index = int(config.get("slide_index", 0))
    dest = config.get("dest")

    audio_file_path = None
    ppt_file_filename = os.path.basename(ppt_file_path)
    ppt_file_localhost_path = get_vm_file(env, {"path": ppt_file_path, "dest": ppt_file_filename})

    if not ppt_file_localhost_path or not os.path.exists(ppt_file_localhost_path):
        return None

    try:
        with zipfile.ZipFile(ppt_file_localhost_path, "r") as myzip:
            slide1_rels_file = "ppt/slides/_rels/slide{}.xml.rels".format(slide_index + 1)
            if slide1_rels_file in myzip.namelist():
                with myzip.open(slide1_rels_file) as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    namespaces = {
                        "r": "http://schemas.openxmlformats.org/package/2006/relationships"
                    }
                    for rel in root.findall("r:Relationship", namespaces):
                        if "audio" in rel.attrib["Type"]:
                            target = rel.attrib["Target"]
                            if target.startswith(".."):
                                audio_file_path = os.path.normpath(
                                    os.path.join("ppt/slides", target)
                                )
                                audio_file_path = audio_file_path.replace("\\", "/")
                                tmpdirname = os.path.dirname(ppt_file_localhost_path)
                                myzip.extract(audio_file_path, tmpdirname)
                                audio_file_path = os.path.join(tmpdirname, audio_file_path)
                                return audio_file_path
                            else:
                                if target.startswith("file://"):
                                    audio_file_path = target[7:]
                                else:
                                    audio_file_path = target
                            break
    except Exception as e:
        logger.error(f"Error processing pptx: {e}")
        return None

    if audio_file_path is None:
        return None
    else:
        return get_vm_file(env, {"path": audio_file_path, "dest": dest})
