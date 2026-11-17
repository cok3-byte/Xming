#
# Copyright (c) 2005 Alexander Gottwald
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE ABOVE LISTED COPYRIGHT HOLDER(S) BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
#
# Except as contained in this notice, the name(s) of the above copyright
# holders shall not be used in advertising or otherwise to promote the sale,
# use or other dealings in this Software without prior written authorization.
#
# Compilación nativa con MSYS2 (MINGW32): la invoca winbuild/build.sh después de
# "make World", porque necesita la libX11 que deja en exports/lib.

CXX = g++
WINDRES = windres

OS_FLAGS = -DUNICODE -D_UNICODE -DWINVER=0x0601 -D_WIN32_WINNT=0x0601 -D_WIN32_IE=0x0800
X11_DIR = ../../../../../exports
X11_INCLUDE = -I$(X11_DIR)/include
X11_LIBS = $(X11_DIR)/lib/libX11.a $(X11_DIR)/lib/libXau.a $(X11_DIR)/lib/libXdmcp.a -lws2_32

CXXFLAGS = -O2 -std=gnu++98 -fpermissive -Wno-write-strings $(OS_FLAGS) $(X11_INCLUDE)
# Runtime de C++ y de gcc estáticos: así no hay que distribuir sus DLL.
LDFLAGS = -mwindows -s -static -static-libgcc -static-libstdc++
LIBS = -lhtmlhelp -lcomctl32 -lole32 -loleaut32 -luuid $(X11_LIBS)

all: XLaunch.exe

%.o: %.cc
	$(CXX) $(CXXFLAGS) -c -o $@ $<

%.res: %.rc
	$(WINDRES) -I resources -O coff -o $@ $<

# X2.bmp (logotipo del diálogo) no venía en el código publicado; se generó una vez
# desde ../X.ico con winbuild/ico2bmp.py y se versiona.

WINDOW_PARTS = window util dialog wizard
WINDOW_OBJECTS = $(foreach file,$(WINDOW_PARTS),window/$(file).o)

RESOURCES_IMAGES = resources/multiwindow.bmp resources/fullscreen.bmp \
	resources/windowed.bmp resources/nodecoration.bmp

resources/resources.res: resources/resources.rc resources/resources.h \
	resources/images.rc resources/dialog.rc resources/strings.rc resources/version.rc \
	$(RESOURCES_IMAGES) X2.bmp

XLaunch.exe: $(WINDOW_OBJECTS) main.o config.o file.o resources/resources.res
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $^ $(LIBS)

clean:
	rm -f XLaunch.exe *.o window/*.o resources/*.res

window/dialog.o: window/dialog.cc window/dialog.h window/window.h window/util.h
window/util.o: window/util.cc window/util.h
window/window.o: window/window.cc window/window.h window/util.h
window/wizard.o: window/wizard.cc window/wizard.h window/dialog.h \
  window/window.h window/util.h
main.o: main.cc window/util.h window/wizard.h window/dialog.h \
  window/window.h resources/resources.h config.h
config.o: config.cc config.h
file.o: file.cc
