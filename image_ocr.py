import os

import easyocr
import re
import magic
from pdf2image import convert_from_path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib import colors


def mapper_closure(factor, unit):
    def wrapper(x):
        return int(x * factor / unit) * unit

    return wrapper


class ImageReader:
    def __init__(
            self,
            languages: list[str],
            gpu: bool = True,
            postprocessor=None
    ):
        print("Model loading.")
        self.reader = easyocr.Reader(languages, gpu=gpu)
        self.postprocessor = postprocessor if postprocessor is not None else lambda x: x
        self.image_w = 0
        self.image_h = 0
        self.image_path = ""
        self.is_first = True

    def pdf_image_conversion(self, pdf_path):
        pdf_name = re.findall(r'([^/]*/)*([^.]*)\.pdf', pdf_path)[-1][-1]
        os.mkdir(pdf_name)
        images = convert_from_path(pdf_path, 300)
        for i, image in enumerate(images):
            image.save(f'{pdf_name}/page_{i + 1}.jpg', 'JPEG')
        return pdf_name

    def read_image(self, path, lattice_fit: int = 1, target_size=A4):
        self.image_path = path
        with open(path, "rb") as f:
            m = magic.from_buffer(f.read(2048))
        img_w, img_h = map(int, re.findall(r', (\d+)\s?x\s?(\d+)', m)[0])
        self.image_w, self.image_h = img_w, img_h
        if target_size is None:
            tar_w, tar_h = self.image_w, self.image_h
        else:
            tar_w, tar_h = target_size
        # calculate scale factor
        if img_w * tar_h < img_h * tar_w:
            f = tar_h / img_h
        else:
            f = tar_w / img_w
        segments = self.reader.readtext(path)
        postprocessed = []
        for seg in segments:
            [_, [dx, dy], _, [x, y]], text, _ = seg
            # ((x, y, w, h), text)
            mapper_c = mapper_closure(f, lattice_fit)
            mapper_d = mapper_closure(f, 2)
            postprocessed.append((
                (
                    mapper_c(x),
                    mapper_c(img_h - y) + tar_h // 2 - mapper_d(img_h / 2),
                    mapper_d(dx - x),
                    mapper_d(y - dy)
                ),
                self.postprocessor(text)
            ))
        return postprocessed

    def write_pdf(self, segments, target_size=A4):
        image_mode = target_size is None
        if target_size is None:
            target_size = (self.image_w, self.image_h)
        if self.is_first:
            self.is_first = False
        else:
            self.canv.showPage()
        self.canv.setPageSize(target_size)
        if image_mode:
            self.canv.setFillColorRGB(0, 0, 0, alpha=1)
            self.canv.drawImage(self.image_path, 0, 0, width=self.image_w, height=self.image_h)
            self.canv.saveState()
        for seg in segments:
            self.canv.setFillColorRGB(0, 0, 0, alpha=0)
            self.canv.saveState()
            (x, y, w, h), text = seg
            self.canv.setFont("Pretendard", int(h * 3 / 4))
            self.canv.rect(*seg[0], stroke=1)
            self.canv.setFillColorRGB(0, 0, 0, alpha=0)
            self.canv.setFont("Pretendard", int(h * 3 / 4))
            # 문자 단위로 쪼개기
            # empty = (w - self.canv.stringWidth(text, "Pretendard", int(h * 3 / 4))) / len(text)
            # if empty > 0:
            #     dx = 0
            #     for c in text:
            #         self.canv.drawString(x + dx, y + h - int(h * 3 / 4), c)
            #         dx += empty + self.canv.stringWidth(c, "Pretendard", int(h * 3 / 4))
            # else:
            #     self.canv.drawString(x, y, text)

            # textObject 사용
            text_obj = self.canv.beginText(x, y + h - int(h * 3 / 4))
            text_obj.setFont("Pretendard", int(h * 3 / 4))
            char_space = (w - self.canv.stringWidth(text, "Pretendard", int(h * 3 / 4))) / len(text)
            text_obj.setCharSpace(char_space)
            text_obj.textLine(text)
            self.canv.drawText(text_obj)

            # paragraph 이용 (안됨)
            # empty = w - self.canv.stringWidth(text, "Pretendard", int(h * 3 / 4))
            # style = ParagraphStyle(
            #     name='justified',
            #     alignment=TA_JUSTIFY,
            #     fontName='Pretendard',
            #     fontSize=int(h * 3 / 4),
            #     textColor=colors.Color(1, 0, 0, alpha=0),
            # )
            # p = Paragraph(text, style)
            # p.wrapOn(self.canv, w, h)
            # p.drawOn(self.canv, x, y + h - p.height)
            # self.canv.restoreState()

    def work_image_sequence(
            self,
            input_dir,
            output_file_name,
            target_size=A4
    ):
        output_file_name = re.sub(r'[$/:\\?"><|]', '', output_file_name)
        if not output_file_name.endswith(".pdf"):
            output_file_name += ".pdf"
        pdfmetrics.registerFont(TTFont("Pretendard", "Pretendard-Regular.ttf"))
        self.canv = canvas.Canvas(f"{input_dir}/{output_file_name}", pagesize=target_size)
        file_list = os.listdir(input_dir)
        ww = len(str(len(file_list)))
        for i in range(len(file_list)):
            print(f"\r[{i + 1:{ww}}/{len(file_list)}] '{file_list[i]}'", end=" ")
            if not file_list[i].endswith((".jpg", ".png")):
                print("is not image.", end="")
                continue
            self.write_pdf(
                self.read_image(f"{input_dir}/{file_list[i]}", lattice_fit=5, target_size=target_size),
                target_size=target_size
            )
        self.canv.save()


r = ImageReader([x for x in input("인식언어 (공백으로 분리): ").split()])

r.work_image_sequence(
    r.pdf_image_conversion(input("PDF 파일 경로: ")),
    input("출력 파일 이름: "),
    None
)
