"""Sonda GLX 1.3 con ctypes (no necesita compilador). La lanza gltest.py dentro de WSL:
    DISPLAY=... LIBGL_ALWAYS_INDIRECT=1 python3 glx13probe.py
Imprime una línea "clave=valor" por comprobación.
"""
import ctypes as C
import time

x = C.CDLL("libX11.so.6")
gl = C.CDLL("libGL.so.1")
vp = C.c_void_p

x.XOpenDisplay.restype = vp
x.XOpenDisplay.argtypes = [C.c_char_p]
x.XRootWindow.restype = C.c_ulong
x.XRootWindow.argtypes = [vp, C.c_int]
x.XCreateColormap.restype = C.c_ulong
x.XCreateColormap.argtypes = [vp, C.c_ulong, vp, C.c_int]
x.XCreateWindow.restype = C.c_ulong
x.XCreateWindow.argtypes = [vp, C.c_ulong, C.c_int, C.c_int, C.c_uint, C.c_uint, C.c_uint,
                            C.c_int, C.c_uint, vp, C.c_ulong, vp]
x.XMapWindow.argtypes = [vp, C.c_ulong]
x.XDestroyWindow.argtypes = [vp, C.c_ulong]
x.XSync.argtypes = [vp, C.c_int]


class XVisualInfo(C.Structure):
    _fields_ = [("visual", vp), ("visualid", C.c_ulong), ("screen", C.c_int), ("depth", C.c_int),
                ("c_class", C.c_int), ("red_mask", C.c_ulong), ("green_mask", C.c_ulong),
                ("blue_mask", C.c_ulong), ("colormap_size", C.c_int), ("bits_per_rgb", C.c_int)]


class XSetWindowAttributes(C.Structure):
    _fields_ = [("background_pixmap", C.c_ulong), ("background_pixel", C.c_ulong),
                ("border_pixmap", C.c_ulong), ("border_pixel", C.c_ulong),
                ("bit_gravity", C.c_int), ("win_gravity", C.c_int), ("backing_store", C.c_int),
                ("backing_planes", C.c_ulong), ("backing_pixel", C.c_ulong),
                ("save_under", C.c_int), ("event_mask", C.c_long),
                ("do_not_propagate_mask", C.c_long), ("override_redirect", C.c_int),
                ("colormap", C.c_ulong), ("cursor", C.c_ulong)]


ERRORS = []
ERRFUNC = C.CFUNCTYPE(C.c_int, vp, vp)


@ERRFUNC
def on_error(d, ev):
    # XErrorEvent: type, display, resourceid, serial, error_code (uchar), request_code, minor_code
    raw = C.cast(ev, C.POINTER(C.c_ubyte * 48)).contents
    ERRORS.append(bytes(raw[32:35]).hex())
    return 0


x.XSetErrorHandler(on_error)

gl.glXChooseFBConfig.restype = C.POINTER(vp)
gl.glXChooseFBConfig.argtypes = [vp, C.c_int, C.POINTER(C.c_int), C.POINTER(C.c_int)]
gl.glXGetVisualFromFBConfig.restype = C.POINTER(XVisualInfo)
gl.glXGetVisualFromFBConfig.argtypes = [vp, vp]
gl.glXCreateWindow.restype = C.c_ulong
gl.glXCreateWindow.argtypes = [vp, vp, C.c_ulong, vp]
gl.glXDestroyWindow.argtypes = [vp, C.c_ulong]
gl.glXCreateNewContext.restype = vp
gl.glXCreateNewContext.argtypes = [vp, vp, C.c_int, vp, C.c_int]
gl.glXMakeContextCurrent.argtypes = [vp, C.c_ulong, C.c_ulong, vp]
gl.glXQueryDrawable.argtypes = [vp, C.c_ulong, C.c_int, C.POINTER(C.c_uint)]
gl.glXGetContextIDEXT.restype = C.c_ulong
gl.glXGetContextIDEXT.argtypes = [vp]
gl.glXImportContextEXT.restype = vp
gl.glXImportContextEXT.argtypes = [vp, C.c_ulong]
gl.glXQueryContextInfoEXT.argtypes = [vp, vp, C.c_int, C.POINTER(C.c_int)]
gl.glXGetFBConfigAttrib.argtypes = [vp, vp, C.c_int, C.POINTER(C.c_int)]
gl.glXSwapBuffers.argtypes = [vp, C.c_ulong]
gl.glXDestroyContext.argtypes = [vp, vp]
gl.glReadPixels.argtypes = [C.c_int, C.c_int, C.c_int, C.c_int, C.c_uint, C.c_uint, vp]

GLX_RENDER_TYPE, GLX_RGBA_BIT, GLX_DRAWABLE_TYPE, GLX_WINDOW_BIT = 0x8011, 1, 0x8010, 1
GLX_DOUBLEBUFFER, GLX_RGBA_TYPE, GLX_FBCONFIG_ID, GLX_WIDTH, GLX_HEIGHT = 5, 0x8014, 0x8013, 0x801D, 0x801E
GLX_SCREEN_EXT = 0x800C

dpy = x.XOpenDisplay(None)
scr = x.XDefaultScreen(vp(dpy))
attrs = (C.c_int * 9)(GLX_RENDER_TYPE, GLX_RGBA_BIT, GLX_DRAWABLE_TYPE, GLX_WINDOW_BIT,
                      GLX_DOUBLEBUFFER, 1, 0, 0, 0)
n = C.c_int()
cfgs = gl.glXChooseFBConfig(dpy, scr, attrs, C.byref(n))
print(f"fbconfigs_window_rgba_db={n.value}")
cfg = cfgs[0]
vi = gl.glXGetVisualFromFBConfig(dpy, cfg).contents
root = x.XRootWindow(dpy, scr)
swa = XSetWindowAttributes()
swa.colormap = x.XCreateColormap(dpy, root, vi.visual, 0)
swa.border_pixel = 0
CWBorderPixel, CWColormap = 1 << 3, 1 << 13
win = x.XCreateWindow(dpy, root, 0, 0, 64, 48, 0, vi.depth, 1, vi.visual,
                      CWBorderPixel | CWColormap, C.byref(swa))
x.XMapWindow(dpy, win)
x.XSync(dpy, 0)
time.sleep(1)

glxwin = gl.glXCreateWindow(dpy, cfg, win, None)
ctx = gl.glXCreateNewContext(dpy, cfg, GLX_RGBA_TYPE, None, 1)
x.XSync(dpy, 0)
print(f"create_errors={','.join(ERRORS) or 'none'}")
ok = gl.glXMakeContextCurrent(dpy, glxwin, glxwin, ctx)
x.XSync(dpy, 0)
print(f"make_current={ok} errors={','.join(ERRORS) or 'none'}")

gl.glClearColor(C.c_float(1.0), C.c_float(0.0), C.c_float(0.0), C.c_float(1.0))
gl.glClear(0x4000)  # GL_COLOR_BUFFER_BIT
gl.glFinish()
px = (C.c_ubyte * 4)()
gl.glReadBuffer(0x0405)  # GL_BACK
gl.glReadPixels(10, 10, 1, 1, 0x1908, 0x1401, px)  # GL_RGBA, GL_UNSIGNED_BYTE
print(f"pixel={px[0]},{px[1]},{px[2]}")
gl.glXSwapBuffers(dpy, glxwin)

w, h = C.c_uint(), C.c_uint()
gl.glXQueryDrawable(dpy, glxwin, GLX_WIDTH, C.byref(w))
gl.glXQueryDrawable(dpy, glxwin, GLX_HEIGHT, C.byref(h))
print(f"drawable_size={w.value}x{h.value}")

# glXImportContextEXT desde otra conexión usa glXQueryContext (GLX 1.3)
cid = gl.glXGetContextIDEXT(ctx)
dpy2 = x.XOpenDisplay(None)
x.XSetErrorHandler(on_error)
imp = gl.glXImportContextEXT(dpy2, cid)
fb, sc = C.c_int(-1), C.c_int(-1)
if imp:
    gl.glXQueryContextInfoEXT(dpy2, imp, GLX_FBCONFIG_ID, C.byref(fb))
    gl.glXQueryContextInfoEXT(dpy2, imp, GLX_SCREEN_EXT, C.byref(sc))
want = C.c_int()
gl.glXGetFBConfigAttrib(dpy, cfg, GLX_FBCONFIG_ID, C.byref(want))
print(f"import_context={'ok' if imp and fb.value == want.value and sc.value == scr else 'fail'}"
      f" fbconfig={fb.value:#x}/{want.value:#x} screen={sc.value}")

gl.glXMakeContextCurrent(dpy, 0, 0, None)
ERRORS.clear()
gl.glXDestroyWindow(dpy, glxwin)
x.XSync(dpy, 0)
print(f"destroy_window_errors={','.join(ERRORS) or 'none'}")

# Destruir la ventana X con una GLXWindow viva libera también la GLXWindow
glxwin2 = gl.glXCreateWindow(dpy, cfg, win, None)
x.XSync(dpy, 0)
x.XDestroyWindow(dpy, win)
x.XSync(dpy, 0)
ERRORS.clear()
gl.glXDestroyWindow(dpy, glxwin2)  # ya no existe: GLXBadWindow
x.XSync(dpy, 0)
print(f"glxwindow_freed_with_window={'yes' if ERRORS else 'no'}")
gl.glXDestroyContext(dpy, ctx)
x.XSync(dpy, 0)
print("done=1")
