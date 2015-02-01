import io
import itertools
import operator
import subprocess

try:
    from PIL import Image
except:
    PIL_AVAILABLE = False
else:
    PIL_AVAILABLE = True

def check_digit(tracking_number):
    """
    Calculates the check digit for the given tracking number.

    See chapter 3.2.1 in
    https://gls-group.eu/DE/media/downloads/GLS_Uni-Box_TechDoku_2D_V0110_01-10-2012_DE-download-4424.pdf
    """
    check_digit = 10 - ((sum(itertools.starmap(operator.mul, zip(itertools.cycle((3, 1)), map(int, str(tracking_number))))) + 1) % 10)
    if check_digit == 10:
        check_digit = 0
    return check_digit

def convert_to_png(pdf):
    proc = subprocess.Popen(
        ["gs", "-q", "-sDEVICE=pngalpha", "-sOutputFile=%stdout%", "-r216", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE
    )
    return proc.communicate(pdf)[0]

def cut_label(png):
    if not PIL_AVAILABLE:
        return png

    img = Image.open(io.BytesIO(png))
    target = Image.new("RGB", (800, 1200), (255, 255, 255))

    crop_width = max(0, img.size[0] - target.size[0]) // 2
    for i in range(img.size[1]):
        if img.getpixel((img.size[0] // 2, i))[0:3] != (255, 255, 255):
            break
    crop_height = max(0, i-8)
    img = img.crop((
        crop_width,
        crop_height,
        target.size[0] + crop_width,
        img.size[1]
    ))

    img2 = Image.new("RGB", img.size)
    def map_pixel(pixel):
        if pixel[3] == 0:
            return (255, 255, 255)

        intensity = 0.299 * pixel[0] + 0.587  * pixel[1] + 0.114 * pixel[2]
        if intensity < 127 and pixel[3] > 127:
            return (0, 0, 0)
        else:
            return (255, 255, 255)
    img2.putdata(list(map(map_pixel, img.getdata())))

    target.paste(img2, (0, 0, img2.size[0], img2.size[1]))

    buf = io.BytesIO()
    target.save(buf, "PNG")
    return buf.getvalue()
