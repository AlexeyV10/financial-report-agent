"""Replaceable render-only backend; PDFium never establishes admission."""
import base64, io
from common import pixel_rect
class PdfiumRenderer:
    def render(self,adapter,zoom,rotation,dpi):
        import pypdfium2 as pdfium
        from PIL import ImageDraw
        adapter.verify();scale=zoom*dpi
        with pdfium.PdfDocument(str(adapter.pdf)) as doc:
            page=doc[0];bitmap=page.render(scale=scale,rotation=rotation)
            image=bitmap.to_pil().convert('RGB')
            rect=pixel_rect(adapter.manifest['cells']['operating_profit-own'],420,360,rotation,scale)
            draw=ImageDraw.Draw(image);draw.rectangle(rect,outline=(0,140,65),width=max(2,round(2*scale)))
            stream=io.BytesIO();image.save(stream,format='PNG');bitmap.close();page.close()
        return dict(png=base64.b64encode(stream.getvalue()).decode('ascii'),width=image.width,height=image.height,rect=rect,page=1,sha256=adapter.manifest['sha256'],zoom=zoom,dpi=dpi,rotation=rotation)
