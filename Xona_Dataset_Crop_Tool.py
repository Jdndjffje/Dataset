#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple
import tkinter as tk
from tkinter import messagebox

try:
    from PIL import Image, ImageTk, ImageOps
except ImportError:
    raise SystemExit('Pillow is required. Run: py -m pip install pillow')

SOURCE_DIR = Path(r'C:\Users\Justx\OneDrive\Documents\Helios Stuff\Dataset\Full_Positive')
OUTPUT_DIR = Path(r'C:\Users\Justx\OneDrive\Documents\Helios Stuff\Dataset\Cropped_Positive')
SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'}


class CropTool:
    HANDLE_RADIUS = 7
    MIN_CROP_SIZE = 8

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Xona's DBD Dataset Crop Tool")
        self.root.geometry('1450x900')
        self.root.minsize(950, 650)
        self.root.configure(bg='#171717')

        self.images = self._find_images()
        self.index = 0
        self.original_image: Optional[Image.Image] = None
        self.display_image: Optional[Image.Image] = None
        self.tk_image: Optional[ImageTk.PhotoImage] = None
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.crop_box: Optional[Tuple[float, float, float, float]] = None
        self.drag_mode: Optional[str] = None
        self.drag_start = (0.0, 0.0)
        self.drag_original: Optional[Tuple[float, float, float, float]] = None

        self._build_ui()
        self._bind_events()

        if not self.images:
            messagebox.showerror('No images found', f'No supported images were found in:\n{SOURCE_DIR}')
            self.root.after(100, self.root.destroy)
            return

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.load_image(0)

    def _find_images(self) -> list[Path]:
        if not SOURCE_DIR.exists():
            messagebox.showerror('Source folder missing', f'The source folder does not exist:\n{SOURCE_DIR}')
            return []
        return sorted(
            [p for p in SOURCE_DIR.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS],
            key=lambda p: p.name.lower(),
        )

    def _build_ui(self) -> None:
        self.canvas = tk.Canvas(self.root, bg='#111111', highlightthickness=0, cursor='crosshair')
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        side = tk.Frame(self.root, width=290, bg='#222222')
        side.pack(side=tk.RIGHT, fill=tk.Y)
        side.pack_propagate(False)

        tk.Label(side, text='DBD Crop Tool', font=('Segoe UI', 18, 'bold'), fg='white', bg='#222222').pack(pady=(18, 4))
        self.file_label = tk.Label(side, text='', font=('Segoe UI', 10), fg='#dddddd', bg='#222222', wraplength=255, justify='center')
        self.file_label.pack(padx=15, pady=(0, 6))
        self.progress_label = tk.Label(side, text='', font=('Segoe UI', 10, 'bold'), fg='#8fd3ff', bg='#222222')
        self.progress_label.pack(pady=(0, 12))

        crop_info = tk.LabelFrame(side, text='Current Crop', font=('Segoe UI', 10, 'bold'), fg='white', bg='#222222', bd=1)
        crop_info.pack(fill=tk.X, padx=15, pady=8)
        self.size_label = tk.Label(crop_info, text='No crop selected', font=('Consolas', 12, 'bold'), fg='#ffe08a', bg='#222222')
        self.size_label.pack(pady=10)

        exact = tk.LabelFrame(side, text='Exact Crop Size', font=('Segoe UI', 10, 'bold'), fg='white', bg='#222222', bd=1)
        exact.pack(fill=tk.X, padx=15, pady=8)
        row = tk.Frame(exact, bg='#222222')
        row.pack(pady=(10, 5))
        tk.Label(row, text='W:', fg='white', bg='#222222').grid(row=0, column=0)
        self.width_entry = tk.Entry(row, width=7, justify='center')
        self.width_entry.grid(row=0, column=1, padx=(3, 10))
        tk.Label(row, text='H:', fg='white', bg='#222222').grid(row=0, column=2)
        self.height_entry = tk.Entry(row, width=7, justify='center')
        self.height_entry.grid(row=0, column=3, padx=(3, 0))
        tk.Button(exact, text='Apply Size to Current Crop', command=self.apply_exact_size, bg='#404040', fg='white', activebackground='#555555', activeforeground='white', relief=tk.FLAT).pack(fill=tk.X, padx=10, pady=(5, 10))

        buttons = tk.Frame(side, bg='#222222')
        buttons.pack(fill=tk.X, padx=15, pady=(12, 5))
        tk.Button(buttons, text='SAVE + NEXT  (Enter)', command=self.save_and_next, font=('Segoe UI', 11, 'bold'), bg='#2c8b57', fg='white', activebackground='#36a66a', activeforeground='white', relief=tk.FLAT, height=2).pack(fill=tk.X, pady=4)
        tk.Button(buttons, text='Save Only  (S)', command=self.save_crop, bg='#34699a', fg='white', activebackground='#417db3', activeforeground='white', relief=tk.FLAT).pack(fill=tk.X, pady=4)

        nav = tk.Frame(buttons, bg='#222222')
        nav.pack(fill=tk.X, pady=4)
        tk.Button(nav, text='← Previous', command=self.previous_image, bg='#444444', fg='white', activebackground='#555555', activeforeground='white', relief=tk.FLAT).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        tk.Button(nav, text='Next →', command=self.next_image, bg='#444444', fg='white', activebackground='#555555', activeforeground='white', relief=tk.FLAT).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
        tk.Button(buttons, text='Reset Crop  (R)', command=self.reset_crop, bg='#6b4c35', fg='white', activebackground='#805c40', activeforeground='white', relief=tk.FLAT).pack(fill=tk.X, pady=4)

        instructions = (
            'Drag to create a crop.\n'
            'Drag inside it to move it.\n'
            'Drag a corner to resize it.\n\n'
            'Enter = save + next\n'
            'S = save only\n'
            'R = reset crop\n'
            'Left/Right = navigate\n\n'
            'The crop is saved automatically with the same filename in Cropped_Positive. The original is never modified.'
        )
        tk.Label(side, text=instructions, font=('Segoe UI', 9), fg='#cfcfcf', bg='#222222', justify=tk.LEFT, wraplength=250).pack(fill=tk.X, padx=20, pady=(15, 10))
        self.status_label = tk.Label(side, text='', font=('Segoe UI', 9, 'bold'), fg='#9ee6b8', bg='#222222', wraplength=255, justify='center')
        self.status_label.pack(side=tk.BOTTOM, padx=12, pady=18)

    def _bind_events(self) -> None:
        self.canvas.bind('<Configure>', lambda _e: self.redraw())
        self.canvas.bind('<ButtonPress-1>', self.on_mouse_down)
        self.canvas.bind('<B1-Motion>', self.on_mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_mouse_up)
        self.root.bind('<Return>', lambda _e: self.save_and_next())
        self.root.bind('<KP_Enter>', lambda _e: self.save_and_next())
        self.root.bind('<KeyPress-s>', lambda _e: self.save_crop())
        self.root.bind('<KeyPress-S>', lambda _e: self.save_crop())
        self.root.bind('<KeyPress-r>', lambda _e: self.reset_crop())
        self.root.bind('<KeyPress-R>', lambda _e: self.reset_crop())
        self.root.bind('<Left>', lambda _e: self.previous_image())
        self.root.bind('<Right>', lambda _e: self.next_image())

    def load_image(self, index: int) -> None:
        self.index = max(0, min(index, len(self.images) - 1))
        path = self.images[self.index]
        try:
            img = ImageOps.exif_transpose(Image.open(path))
            self.original_image = img.convert('RGB')
        except Exception as exc:
            messagebox.showerror('Image error', f'Could not open:\n{path}\n\n{exc}')
            return
        self.crop_box = None
        self.file_label.config(text=path.name)
        self.progress_label.config(text=f'{self.index + 1} / {len(self.images)}')
        self.status_label.config(text='')
        self.size_label.config(text='No crop selected')
        self.redraw()

    def redraw(self) -> None:
        if self.original_image is None:
            return
        cw, ch = max(self.canvas.winfo_width(), 1), max(self.canvas.winfo_height(), 1)
        iw, ih = self.original_image.size
        self.scale = min(cw / iw, ch / ih)
        dw, dh = max(1, int(iw * self.scale)), max(1, int(ih * self.scale))
        self.offset_x, self.offset_y = (cw - dw) // 2, (ch - dh) // 2
        self.display_image = self.original_image.resize((dw, dh), Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(self.display_image)
        self.canvas.delete('all')
        self.canvas.create_image(self.offset_x, self.offset_y, anchor=tk.NW, image=self.tk_image)
        if self.crop_box:
            self.draw_crop_overlay()

    def image_bounds(self) -> Tuple[float, float, float, float]:
        if self.display_image is None:
            return 0, 0, 0, 0
        w, h = self.display_image.size
        return float(self.offset_x), float(self.offset_y), float(self.offset_x + w), float(self.offset_y + h)

    def clamp(self, x: float, y: float) -> Tuple[float, float]:
        l, t, r, b = self.image_bounds()
        return min(max(x, l), r), min(max(y, t), b)

    @staticmethod
    def normalize(box: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
        x1, y1, x2, y2 = box
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)

    def get_mode(self, x: float, y: float) -> Optional[str]:
        if not self.crop_box:
            return None
        x1, y1, x2, y2 = self.normalize(self.crop_box)
        handles = {'nw': (x1, y1), 'ne': (x2, y1), 'sw': (x1, y2), 'se': (x2, y2)}
        for name, (hx, hy) in handles.items():
            if abs(x - hx) <= self.HANDLE_RADIUS * 2 and abs(y - hy) <= self.HANDLE_RADIUS * 2:
                return name
        if x1 <= x <= x2 and y1 <= y <= y2:
            return 'move'
        return None

    def on_mouse_down(self, event: tk.Event) -> None:
        x, y = self.clamp(event.x, event.y)
        self.drag_start = (x, y)
        self.drag_original = self.crop_box
        self.drag_mode = self.get_mode(x, y) or 'new'
        if self.drag_mode == 'new':
            self.crop_box = (x, y, x, y)

    def on_mouse_drag(self, event: tk.Event) -> None:
        if not self.drag_mode:
            return
        x, y = self.clamp(event.x, event.y)
        sx, sy = self.drag_start
        if self.drag_mode == 'new':
            self.crop_box = (sx, sy, x, y)
        elif self.drag_mode == 'move' and self.drag_original:
            ox1, oy1, ox2, oy2 = self.normalize(self.drag_original)
            dx, dy = x - sx, y - sy
            l, t, r, b = self.image_bounds()
            w, h = ox2 - ox1, oy2 - oy1
            nx1 = min(max(ox1 + dx, l), r - w)
            ny1 = min(max(oy1 + dy, t), b - h)
            self.crop_box = (nx1, ny1, nx1 + w, ny1 + h)
        elif self.drag_original:
            x1, y1, x2, y2 = self.normalize(self.drag_original)
            if self.drag_mode == 'nw': self.crop_box = (x, y, x2, y2)
            elif self.drag_mode == 'ne': self.crop_box = (x1, y, x, y2)
            elif self.drag_mode == 'sw': self.crop_box = (x, y1, x2, y)
            elif self.drag_mode == 'se': self.crop_box = (x1, y1, x, y)
        self.draw_crop_overlay()
        self.update_size_label()

    def on_mouse_up(self, _event: tk.Event) -> None:
        if self.crop_box:
            x1, y1, x2, y2 = self.normalize(self.crop_box)
            if x2 - x1 < self.MIN_CROP_SIZE or y2 - y1 < self.MIN_CROP_SIZE:
                self.crop_box = None
        self.drag_mode = None
        self.drag_original = None
        self.draw_crop_overlay()
        self.update_size_label()

    def draw_crop_overlay(self) -> None:
        for tag in ('shade', 'crop', 'handle'):
            self.canvas.delete(tag)
        if not self.crop_box:
            return
        x1, y1, x2, y2 = self.normalize(self.crop_box)
        l, t, r, b = self.image_bounds()
        kwargs = dict(fill='#000000', stipple='gray50', outline='', tags='shade')
        self.canvas.create_rectangle(l, t, r, y1, **kwargs)
        self.canvas.create_rectangle(l, y2, r, b, **kwargs)
        self.canvas.create_rectangle(l, y1, x1, y2, **kwargs)
        self.canvas.create_rectangle(x2, y1, r, y2, **kwargs)
        self.canvas.create_rectangle(x1, y1, x2, y2, outline='#00e5ff', width=2, tags='crop')
        for hx, hy in ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):
            rr = self.HANDLE_RADIUS
            self.canvas.create_rectangle(hx-rr, hy-rr, hx+rr, hy+rr, fill='#00e5ff', outline='white', width=1, tags='handle')

    def canvas_to_source(self, box: Tuple[float, float, float, float]) -> Tuple[int, int, int, int]:
        assert self.original_image is not None
        x1, y1, x2, y2 = self.normalize(box)
        iw, ih = self.original_image.size
        sx1 = max(0, min(round((x1 - self.offset_x) / self.scale), iw - 1))
        sy1 = max(0, min(round((y1 - self.offset_y) / self.scale), ih - 1))
        sx2 = max(sx1 + 1, min(round((x2 - self.offset_x) / self.scale), iw))
        sy2 = max(sy1 + 1, min(round((y2 - self.offset_y) / self.scale), ih))
        return sx1, sy1, sx2, sy2

    def source_to_canvas(self, box: Tuple[int, int, int, int]) -> Tuple[float, float, float, float]:
        x1, y1, x2, y2 = box
        return (self.offset_x + x1*self.scale, self.offset_y + y1*self.scale, self.offset_x + x2*self.scale, self.offset_y + y2*self.scale)

    def update_size_label(self) -> None:
        if not self.crop_box:
            self.size_label.config(text='No crop selected')
            return
        x1, y1, x2, y2 = self.canvas_to_source(self.crop_box)
        self.size_label.config(text=f'{x2-x1} × {y2-y1}')

    def apply_exact_size(self) -> None:
        if self.original_image is None:
            return
        try:
            width = int(self.width_entry.get().strip())
            height = int(self.height_entry.get().strip())
            if width <= 0 or height <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning('Invalid size', 'Width and height must be positive whole numbers.')
            return
        iw, ih = self.original_image.size
        width, height = min(width, iw), min(height, ih)
        if self.crop_box:
            x1, y1, x2, y2 = self.canvas_to_source(self.crop_box)
            cx, cy = (x1+x2)//2, (y1+y2)//2
        else:
            cx, cy = iw//2, ih//2
        sx1 = max(0, min(cx - width//2, iw - width))
        sy1 = max(0, min(cy - height//2, ih - height))
        self.crop_box = self.source_to_canvas((sx1, sy1, sx1+width, sy1+height))
        self.draw_crop_overlay()
        self.update_size_label()

    def reset_crop(self) -> None:
        self.crop_box = None
        self.draw_crop_overlay()
        self.update_size_label()
        self.status_label.config(text='Crop reset.', fg='#9ee6b8')

    def save_crop(self) -> bool:
        if self.original_image is None or not self.crop_box:
            self.status_label.config(text='Draw a crop box first.', fg='#ffb0b0')
            return False
        source_path = self.images[self.index]
        crop = self.original_image.crop(self.canvas_to_source(self.crop_box))
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / source_path.name
        try:
            ext = output_path.suffix.lower()
            if ext in {'.jpg', '.jpeg'}:
                crop.save(output_path, quality=95, subsampling=0)
            elif ext == '.webp':
                crop.save(output_path, quality=95, method=6)
            else:
                crop.save(output_path)
        except Exception as exc:
            messagebox.showerror('Save error', f'Could not save:\n{output_path}\n\n{exc}')
            return False
        w, h = crop.size
        self.status_label.config(text=f'Saved {w}×{h}\n{output_path.name}', fg='#9ee6b8')
        return True

    def save_and_next(self) -> None:
        if self.save_crop():
            if self.index < len(self.images) - 1:
                self.load_image(self.index + 1)
            else:
                self.status_label.config(text='Saved. Final image reached.', fg='#9ee6b8')

    def previous_image(self) -> None:
        if self.index > 0:
            self.load_image(self.index - 1)

    def next_image(self) -> None:
        if self.index < len(self.images) - 1:
            self.load_image(self.index + 1)


def main() -> None:
    root = tk.Tk()
    CropTool(root)
    root.mainloop()


if __name__ == '__main__':
    main()
