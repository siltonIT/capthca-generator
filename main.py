from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import string
import random
from PIL import Image, ImageDraw, ImageFont
import io
import uuid

app = FastAPI()
templates = Jinja2Templates(directory="templates")

captcha_store = {}

class CaptchaResponse(BaseModel):
    success: bool
    message: str | None = None
    session_id: str | None = None
    attempts: int | None = None

def generate_captcha_text(length: int = 6) -> str:
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def generate_captcha_image(captcha_text: str) -> tuple[io.BytesIO, str]:
    width, height = 200, 100
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 30)
    except:
        font = ImageFont.load_default()

    for _ in range(2000):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill=(random.randint(150, 255), random.randint(150, 255), random.randint(150, 255)))
    
    for _ in range(50):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line((x1, y1, x2, y2), fill=(random.randint(200, 255), random.randint(200, 255), random.randint(200, 255)), width=1)

    def distort_text(text, draw, font, width, height):
        img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        char_width = width // len(text)
        char_height = height

        for i, char in enumerate(text):
            char_img = Image.new("RGBA", (char_width, char_height), (255, 255, 255, 0))
            d_char = ImageDraw.Draw(char_img)
            bbox = font.getbbox(char)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x_pos = (char_width - text_width) // 2
            y_pos = (char_height - text_height) // 2
            d_char.text((x_pos, y_pos), char, font=font, fill=(0, 0, 0, 255))

            angle = random.uniform(-20, 20)
            char_img = char_img.rotate(angle, expand=False)
            x_offset = i * char_width
            img.paste(char_img, (x_offset, 0), char_img)

        return img

    distorted_img = distort_text(captcha_text, draw, font, width, height)
    image.paste(distorted_img, (0, 0), distorted_img)

    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format="PNG")
    img_byte_arr.seek(0)
    return img_byte_arr, captcha_text

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    captcha_text = generate_captcha_text()
    session_id = str(uuid.uuid4())
    captcha_store[session_id] = captcha_text
    response = templates.TemplateResponse("index.html", {"request": request})
    response.set_cookie(key="session_id", value=session_id, max_age=1800)
    return response

@app.get("/success")
async def success(request: Request):
    attempts = request.query_params.get("attempts", "неизвестно")
    return templates.TemplateResponse("success.html", {"request": request, "attempts": attempts})

@app.get("/captcha-image")
async def get_captcha_image(session_id: str):
    if session_id not in captcha_store:
        raise HTTPException(status_code=400, detail="Сессия капчи не найдена")
    img_byte_arr, _ = generate_captcha_image(captcha_store[session_id])
    return Response(content=img_byte_arr.getvalue(), media_type="image/png")

@app.post("/captcha")
async def verify_captcha(request: Request, response: Response):
    form_data = await request.form()
    user_input = form_data.get("captcha", "")
    attempts = int(form_data.get("attempts", 0)) + 1
    session_id = request.cookies.get("session_id")

    if not session_id or session_id not in captcha_store:
        raise HTTPException(status_code=400, detail="Капча не найдена или истекла")

    stored_captcha = captcha_store[session_id]
    if user_input == stored_captcha:
        del captcha_store[session_id]
        response.delete_cookie("session_id")
        return RedirectResponse(url=f"/success?attempts={attempts}", status_code=303)
    else:
        new_captcha_text = generate_captcha_text()
        new_session_id = str(uuid.uuid4())
        captcha_store[new_session_id] = new_captcha_text
        response.set_cookie(key="session_id", value=new_session_id, max_age=1800)
        return CaptchaResponse(
            success=False,
            message="Неверный код",
            session_id=new_session_id,
            attempts=attempts
        )
