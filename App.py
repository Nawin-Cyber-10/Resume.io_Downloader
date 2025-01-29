import io
import json
import os
import webbrowser
import requests
import streamlit as st
from dataclasses import dataclass, field
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Link  # Updated import for Link
from enum import Enum
from datetime import datetime, timezone
import pytesseract
import fitz  # PyMuPDF

# Configure Tesseract
pytesseract.pytesseract.tesseract_cmd = r'./tesseract.exe'

class Extension(str, Enum):
    jpeg = "jpeg"
    png = "png"
    webp = "webp"

@dataclass
class ResumeioDownloader:
    rendering_token: str
    extension: Extension = field(default_factory=lambda: Extension.jpeg)
    image_size: int = 3000
    METADATA_URL: str = "https://ssr.resume.tools/meta/{rendering_token}?cache={cache_date}"
    IMAGES_URL: str = (
        "https://ssr.resume.tools/to-image/{rendering_token}-{page_id}.{extension}?cache={cache_date}&size={image_size}"
    )

    def __post_init__(self) -> None:
        """Set the cache date to the current time."""
        self.cache_date = datetime.now(timezone.utc).isoformat()[:-9] + "Z"

    def generate_pdf(self) -> bytes:
        self.__get_resume_metadata()
        images = self.__download_images()
        pdf = PdfWriter()
        metadata_w, metadata_h = self.metadata[0].get("viewport").values()
        for i, image in enumerate(images):
            page_pdf = pytesseract.image_to_pdf_or_hocr(image, extension="pdf")
            page = PdfReader(io.BytesIO(page_pdf)).pages[0]
            page_scale = max(page.mediabox.height / metadata_h, page.mediabox.width / metadata_w)
            pdf.add_page(page)
            for link in self.metadata[i].get("links"):
                link_url = link.pop("url")
                link.update((k, v * page_scale) for k, v in link.items())
                x, y, w, h = link.values()
                # Updated to use pypdf.annotations.Link
                annotation = Link(rect=(x, y, x + w, y + h), url=link_url)
                pdf.add_annotation(page_number=i, annotation=annotation)
        with io.BytesIO() as file:
            pdf.write(file)
            return file.getvalue()

    def __get_resume_metadata(self) -> None:
        response = requests.get(
            self.METADATA_URL.format(rendering_token=self.rendering_token, cache_date=self.cache_date),
        )
        self.__raise_for_status(response)
        content = json.loads(response.text)
        self.metadata = content.get("pages")

    def __download_images(self) -> list[Image.Image]:
        images = []
        for page_id in range(1, 1 + len(self.metadata)):
            image_url = self.IMAGES_URL.format(
                rendering_token=self.rendering_token,
                page_id=page_id,
                extension=self.extension.value,  # Ensure we get the string value of the enum
                cache_date=self.cache_date,
                image_size=self.image_size,
            )
            image = self.__download_image_from_url(image_url)
            images.append(image)
        return images

    def __download_image_from_url(self, url) -> Image.Image:
        response = requests.get(url)
        self.__raise_for_status(response)
        return Image.open(io.BytesIO(response.content))

    def __raise_for_status(self, response) -> None:
        if response.status_code != 200:
            raise Exception(
                f"Unable to download resume (rendering token: {self.rendering_token}), status code: {response.status_code}"
            )

# Streamlit UI
def open_link():
    url = "https://resume.io/api/app/resumes"
    try:
        webbrowser.open_new(url)
    except Exception as e:
        st.error(f"Failed to open the link: {str(e)}")

def download_resume():
    rendering_token = st.text_input("Enter your rendering token:")
    if rendering_token:
        try:
            downloader = ResumeioDownloader(rendering_token=rendering_token)
            pdf_bytes = downloader.generate_pdf()

            # Save PDF
            output_filename = f"{rendering_token}_resume.pdf"
            with open(output_filename, "wb") as f:
                f.write(pdf_bytes)

            st.success(f"Resume downloaded successfully as {output_filename}")
            preview_resume(output_filename)
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")

def preview_resume(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        pages_list = [doc.load_page(i) for i in range(len(doc))]
        st.image(render_pdf_page(pages_list[0]))  # Show first page as preview
    except Exception as e:
        st.error(f"Failed to preview the resume: {str(e)}")

def render_pdf_page(page):
    # Convert PDF page to image using PyMuPDF
    pix = page.get_pixmap()
    pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return pil_image

def main():
    st.title("Resume Downloader")
    st.write("1. Click 'Get Rendering Token' to obtain your token.")
    st.write("2. Enter the token and click 'Download Resume'.")
    
    # Button to get rendering token link
    st.button("Get Rendering Token", on_click=open_link)
    
    # Download resume button
    download_resume()

if __name__ == "__main__":
    main()
