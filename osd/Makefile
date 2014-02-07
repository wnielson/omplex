LIBFLAGS=-I/opt/vc/include -I/opt/vc/include/interface/vmcs_host/linux -I/opt/vc/include/interface/vcos/pthreads

all:	libshapes.o oglinit.o libosd.so

libshapes.o:	libs/libshapes.c libs/shapes.h libs/fontinfo.h oglinit.o
	gcc -O2 -Wall $(LIBFLAGS) -c libs/libshapes.c -I./llbs
oglinit.o:	libs/oglinit.c
	gcc -O2 -Wall $(LIBFLAGS) -c libs/oglinit.c -I./llbs
libosd.so:	osd.c oglinit.o libshapes.o
	gcc -shared -Wall -O2 -o libosd.so osd.c libshapes.o oglinit.o -I/opt/vc/include -I/opt/vc/include/interface/vcos/pthreads -I./libs -I./fonts -L/opt/vc/lib -lGLESv2 -ljpeg
osd:	osd.c oglinit.o libshapes.o
	gcc -Wall -O2 -o osd osd.c libshapes.o oglinit.o -I/opt/vc/include -I/opt/vc/include/interface/vcos/pthreads -I./libs -I./fonts -L/opt/vc/lib -lGLESv2 -ljpeg
clean:
	rm -rf libshapes.o oglinit.o libosd.so
