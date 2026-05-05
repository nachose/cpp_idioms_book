import os
import sys
import xml.etree.ElementTree as ET
import zipfile


def update_docx_toc_fields(docx_path):
    # Namespace dictionary for XML parsing
    namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    ET.register_namespace("w", namespaces["w"])  # Register namespace for pretty printing

    temp_docx_path = docx_path + ".tmp"
    settings_xml_name = "word/settings.xml"
    settings_content = None

    # Read the original docx and extract settings.xml
    try:
        with zipfile.ZipFile(docx_path, "r") as zin:
            if settings_xml_name in zin.namelist():
                settings_content = zin.read(settings_xml_name)
            else:
                print(f"Error: {settings_xml_name} not found in {docx_path}", file=sys.stderr)
                return False

            # Parse the XML
            root = ET.fromstring(settings_content)
            settings_element = root

            # Check for w:updateFields
            update_fields_element = settings_element.find("w:updateFields", namespaces)

            if update_fields_element is None:
                # Add w:updateFields if it doesn't exist
                update_fields_element = ET.SubElement(
                    settings_element, "{" + namespaces["w"] + "}updateFields"
                )
                update_fields_element.set("{" + namespaces["w"] + "}val", "true")
                print(f'Added <w:updateFields w:val="true"/> to {settings_xml_name}')
            elif update_fields_element.get("{" + namespaces["w"] + "}val") != "true":
                # Update w:val if it exists but is not "true"
                update_fields_element.set("{" + namespaces["w"] + "}val", "true")
                print(f'Updated <w:updateFields w:val="true"/> in {settings_xml_name}')
            else:
                print(f'<w:updateFields w:val="true"/> already present in {settings_xml_name}')
                # No change needed, so we can skip rewriting the zip
                return True  # Indicate success as no change was needed

            # Convert the modified XML back to a string
            modified_settings_content = ET.tostring(
                root, encoding="UTF-8", xml_declaration=True
            ).decode("utf-8")

            # Create a new zip file and copy all files, replacing settings.xml
            with zipfile.ZipFile(temp_docx_path, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename == settings_xml_name:
                        zout.writestr(item, modified_settings_content)
                    else:
                        zout.writestr(item, zin.read(item.filename))

    except Exception as e:
        print(f"An error occurred during docx processing: {e}", file=sys.stderr)
        if os.path.exists(temp_docx_path):
            os.remove(temp_docx_path)
        return False

    # Replace the original docx file with the temporary one
    try:
        os.replace(temp_docx_path, docx_path)
        print(f"Successfully updated {docx_path}")
        return True
    except Exception as e:
        print(f"Error replacing original docx file: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python update_docx_toc.py <path_to_docx_file>", file=sys.stderr)
        sys.exit(1)

    docx_file = sys.argv[1]
    if not os.path.exists(docx_file):
        print(f"Error: File not found at {docx_file}", file=sys.stderr)
        sys.exit(1)

    if not update_docx_toc_fields(docx_file):
        sys.exit(1)
