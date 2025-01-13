import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uno
from com.sun.star.beans import PropertyValue

app = FastAPI()

class FileRequest(BaseModel):
    file_path: str


def count_pages(file_path: str) -> int:
    try:
        local_context = uno.getComponentContext()
        resolver = local_context.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", local_context
        )
        context = resolver.resolve(
            "uno:socket,host=localhost,port=2002;urp;StarOffice.ComponentContext"
        )
        desktop = context.ServiceManager.createInstanceWithContext(
            "com.sun.star.frame.Desktop", context
        )

        url = uno.systemPathToFileUrl(file_path)
        properties = (PropertyValue("Hidden", 0, True, 0),)
        document = desktop.loadComponentFromURL(url, "_blank", 0, properties)

        try:
            if file_path.endswith(".pdf"):
                return document.getDocumentProperties().TotalPageCount
            elif file_path.endswith(".docx") or file_path.endswith(".doc"):
                return document.Text.getEnd().PageBreakCount + 1
        finally:
            document.close(True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {e}")


@app.post("/count_pages")
async def count_file_pages(request: FileRequest):
    if not os.path.exists(request.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    pages = count_pages(request.file_path)
    return {"pages": pages}
