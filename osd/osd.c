/*
    A simple on-screen display (OSD) which can be displayed ontop of a
    playing video.  The design was modelled after Plex Home Theater's.
    It presents a very simple interface that can be called from within
    Python and relies on the OpenVG library provided by Anthony Starks.

    Build with:

        gcc -shared -Wall -o libosd.so osd.c \
        ../libshapes.o ../oglinit.o \
        -I/opt/vc/include -I/opt/vc/include/interface/vcos/pthreads -I.. \
        -L/opt/vc/lib -lGLESv2 -ljpeg

    Example usage from Python:

        import ctypes
        libosd = ctypes.cdll.LoadLibrary("./libosd.so")
        libosd.show_osd(23,100, "Test Title (2014)")
        libosd.hide_osd()

    Author: Weston Nielson <wnielson@github>
*/
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <VG/openvg.h>
#include <VG/vgu.h>

#include "fontinfo.h"
#include "shapes.h"

#include "OpenSans-Semibold.h"
#include "OpenSans-Bold.h"

Fontinfo OpenSansSemiBold;
Fontinfo OpenSansBold;

typedef struct
{
    char  time_now[10];
    char  time_end[10];
    char  pos_now[10];
    char  pos_end[10];
    
    char* title;
    
    int   duration;
    int   played;

    int   width;
    int   height;
} OSD;

static OSD* MAIN_OSD = NULL;

void get_time(char* output, int seconds)
{
    time_t     rawtime;
    struct tm* timeinfo;

    char period[] = "AM";
    int  hour, minute;

    time(&rawtime);
    timeinfo = localtime(&rawtime);

    hour   = timeinfo->tm_hour;
    minute = timeinfo->tm_min;

    if (seconds > 0)
    {
        // Compute "now" plus "seconds"
        int total_seconds = hour*3600 + minute*60 + seconds;
        hour   = total_seconds/3600;
        minute = (total_seconds-(hour*3600))/60;
    }

    if (hour >= 12)
    {
        period[0] = 'P';
        if (hour != 12)
        {
            hour -= 12;
        }
    }

    sprintf(output, "%.2d:%.2d %.2s", hour, minute, period);
};

void seconds_to_str(char* output, int total_seconds)
{
    int hours    = total_seconds/3600,
        minutes  = (total_seconds-(hours*3600))/60,
        seconds  = total_seconds - (hours*3600) - (minutes*60);

    if (hours > 0)
    {
        sprintf(output, "%.2d:%.2d:%.2d", hours, minutes, seconds);
    }
    else
    {
        sprintf(output, "%.2d:%.2d", minutes, seconds);
    }
};

void init_osd()
{
    if (MAIN_OSD != NULL)
    {
        return;
    }

    MAIN_OSD = (OSD*)malloc(sizeof(OSD));

    init(&MAIN_OSD->width, &MAIN_OSD->height);

    OpenSansSemiBold = loadfont(OpenSansSemibold_glyphPoints,
                            OpenSansSemibold_glyphPointIndices,
                            OpenSansSemibold_glyphInstructions,
                            OpenSansSemibold_glyphInstructionIndices,
                            OpenSansSemibold_glyphInstructionCounts,
                            OpenSansSemibold_glyphAdvances,
                            OpenSansSemibold_characterMap,
                            OpenSansSemibold_glyphCount);

    OpenSansBold = loadfont(OpenSansBold_glyphPoints,
                            OpenSansBold_glyphPointIndices,
                            OpenSansBold_glyphInstructions,
                            OpenSansBold_glyphInstructionIndices,
                            OpenSansBold_glyphInstructionCounts,
                            OpenSansBold_glyphAdvances,
                            OpenSansBold_characterMap,
                            OpenSansBold_glyphCount);
};

void destroy_osd()
{
    if (MAIN_OSD == NULL)
    {
        return;
    }

    unloadfont(OpenSansBold.Glyphs, OpenSansBold.Count);
    unloadfont(OpenSansSemiBold.Glyphs, OpenSansSemiBold.Count);

    finish();
    free(MAIN_OSD);

    MAIN_OSD = NULL;
};

void show_osd(int played, int duration, char* title)
{
    if (MAIN_OSD == NULL)
    {
        // Calling ``init_osd`` everytime seems wasteful, but it is needed to
        // ensure that the OSD is visible.  The main issue is that if the player
        // is stopped and then restarted, the graphics library needs to be
        // reinitalized, otherwise the OSD is not drawn ontop of the video.
        init_osd();
    }

    OSD* osd = MAIN_OSD;

    if (played > duration)
    {
        played = duration;
    }

    osd->duration   = duration;
    osd->played     = played;
    osd->title      = title;

    Start(osd->width, osd->height);

    Fill(255,255,255,1);
    Text(32, 120+82+20, "PAUSED", OpenSansBold, 16);

    // Main OSD background
    Fill(0, 0, 0, 0.5);
    Roundrect(22, 82, osd->width-44, 120, 15, 15);

    ///////////////////////////////////////////////////////////////////////
    // Header
    ///////////////////////////////////////////////////////////////////////
    Fill(0, 0, 0, 1);
    Roundrect(22, 120+82-20, osd->width-44, 20, 15, 15);  // Top of the header
    Rect(22, 120+82-(54+10), osd->width-44, 54);          // Bottom of header

    // Current time
    get_time(osd->time_now, 0);
    Fill(102, 102, 102, 1);
    Text(46, 162, osd->time_now, OpenSansSemiBold, 14);

    // End time
    if (duration > 0)
    {
        get_time(osd->time_end, osd->duration-osd->played);
        TextEnd(osd->width-46, 162, osd->time_end, OpenSansSemiBold, 14);
    }

    // Title text
    Fill(255, 255, 255, 1);
    int title_width = TextWidth(osd->title, OpenSansSemiBold, 20);
    Text((osd->width/2)-(title_width/2), 162, osd->title, OpenSansSemiBold, 20);


    ///////////////////////////////////////////////////////////////////////////

    ///////////////////////////////////////////////////////////////////////////
    // Progress Bar
    ///////////////////////////////////////////////////////////////////////////
    if (duration > 0)
    {
        int   pbar_width = osd->width-288;
        float pct_player = (float)played/duration;
        Fill(255, 255, 255, 0.2);                               // Transparent bg
        Roundrect(142, 102, pbar_width, 12, 10, 10);            // Centered

        Fill(209, 125, 30, 1);                                  // Orange bar (progress)
        Roundrect(142, 102, pbar_width*pct_player, 12, 10, 10); // Left justified

        // Progress text
        seconds_to_str(osd->pos_now, osd->played);
        seconds_to_str(osd->pos_end, osd->duration-osd->played);

        // Text shadow
        Fill(0, 0, 0, 1);
        Text(46-1, 102-1, osd->pos_now, OpenSansSemiBold, 12);
        TextEnd(osd->width-46-1, 102-1, osd->pos_end, OpenSansSemiBold, 12);

        // Actual text
        Fill(255,255,255,1);
        Text(46, 102, osd->pos_now, OpenSansSemiBold, 12);
        TextEnd(osd->width-46, 102, osd->pos_end, OpenSansSemiBold, 12);
    }
    //////////////////////////////////////////////////////////////////////

    End();
}

void hide_osd()
{
    if (MAIN_OSD == NULL)
    {
        return;
    }

    //Start(MAIN_OSD->width, MAIN_OSD->height);
    //End();

    destroy_osd();
};

int main()
{
    char tmp[5];
    show_osd(1023, 2503, "Test Title(2014)");
    gets(tmp);
    hide_osd();
    return 0;
};
