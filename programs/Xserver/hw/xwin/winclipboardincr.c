/*
 * Copyright (C) 2026 Xming-build contributors
 *
 * Permission is hereby granted, free of charge, to any person obtaining a
 * copy of this software and associated documentation files (the
 * "Software"), to deal in the Software without restriction, including
 * without limitation the rights to use, copy, modify, merge, publish,
 * distribute, sublicense, and/or sell copies of the Software, and to
 * permit persons to whom the Software is furnished to do so, subject to
 * the following conditions:
 *
 * The above copyright notice and this permission notice shall be
 * included in all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 * MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 * NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM,
 * DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
 * OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR
 * THE USE OR OTHER DEALINGS IN THE SOFTWARE.
 */

/*
 * Transferencias INCR (ICCCM 2.7.2) del clipboard.
 *
 * Un cliente X que tiene más datos de los que caben en una petición pone en
 * la propiedad el tipo INCR y luego los entrega por trozos: cada vez que el
 * receptor borra la propiedad, el propietario escribe el siguiente trozo; un
 * trozo de longitud 0 marca el final. Sin esto, los textos grandes copiados
 * desde aplicaciones GTK/Qt llegaban vacíos a Windows.
 *
 * Ambas funciones bloquean el hilo del clipboard mientras dura la
 * transferencia, con un timeout por trozo (-clipboardtimeout) y un tamaño
 * máximo (-clipboardmaxsize) para que un cliente lento o malicioso no pueda
 * colgarlo ni agotar la memoria.
 */

#ifdef HAVE_XWIN_CONFIG_H
#include <xwin-config.h>
#endif
#include "winclipboard.h"

extern int		g_iClipboardTimeoutMs;
extern unsigned long	g_ulClipboardMaxBytes;

/* Tamaño de cada trozo enviado a un cliente X */
#define WIN_INCR_CHUNK_SIZE	(256 * 1024)


/*
 * Espera un PropertyNotify con el estado indicado para (window, property).
 * Solo consume eventos PropertyNotify de esa ventana; el resto queda en la
 * cola para el bucle principal del clipboard.
 */

static Bool
winClipboardWaitProperty (Display *pDisplay, Window iWindow, Atom atomProperty,
			  int iState)
{
  DWORD		dwStart = GetTickCount ();
  int		iConnNumber = ConnectionNumber (pDisplay);

  XFlush (pDisplay);

  while (1)
    {
      XEvent		event;
      fd_set		fdsRead;
      struct timeval	tv;
      DWORD		dwElapsed;

      while (XCheckTypedWindowEvent (pDisplay, iWindow, PropertyNotify, &event))
	{
	  if (event.xproperty.atom == atomProperty
	      && event.xproperty.state == iState)
	    return TRUE;
	}

      dwElapsed = GetTickCount () - dwStart;
      if (dwElapsed >= (DWORD) g_iClipboardTimeoutMs)
	return FALSE;

      FD_ZERO (&fdsRead);
      FD_SET (iConnNumber, &fdsRead);
      tv.tv_sec = (g_iClipboardTimeoutMs - dwElapsed) / 1000;
      tv.tv_usec = ((g_iClipboardTimeoutMs - dwElapsed) % 1000) * 1000;

      if (select (iConnNumber + 1, &fdsRead, NULL, NULL, &tv) > 0)
	XEventsQueued (pDisplay, QueuedAfterReading);
    }
}


/*
 * Recibe una selección enviada con INCR en (iWindow, atomProperty).
 * Llamar cuando XGetWindowProperty devuelve el tipo INCR. Si tiene éxito,
 * pxtp->value se reserva con malloc (XFree lo libera: Xlib usa free).
 */

Bool
winClipboardReadIncr (Display *pDisplay, Window iWindow, Atom atomProperty,
		      XTextProperty *pxtp)
{
  unsigned char	*pData = NULL;
  unsigned long	ulLen = 0;
  Atom		atomType = None;
  Bool		fOk = FALSE;

  /*
   * Escuchar los cambios de la propiedad antes de borrarla: el borrado es la
   * señal para que el propietario empiece a enviar.
   */
  XSelectInput (pDisplay, iWindow, PropertyChangeMask);
  XDeleteProperty (pDisplay, iWindow, atomProperty);

  while (1)
    {
      Atom		atomChunkType;
      int		iFormat;
      unsigned long	ulItems, ulBytesLeft, ulBytes;
      unsigned char	*pChunk = NULL;
      unsigned char	*pNew;

      if (!winClipboardWaitProperty (pDisplay, iWindow, atomProperty,
				     PropertyNewValue))
	{
	  ErrorF ("winClipboardReadIncr - timeout esperando un trozo "
		  "(%lu bytes recibidos)\n", ulLen);
	  break;
	}

      if (XGetWindowProperty (pDisplay, iWindow, atomProperty,
			      0, 0x1FFFFFFF, True, AnyPropertyType,
			      &atomChunkType, &iFormat, &ulItems,
			      &ulBytesLeft, &pChunk) != Success)
	{
	  ErrorF ("winClipboardReadIncr - XGetWindowProperty falló\n");
	  break;
	}

      /* Trozo vacío: fin de la transferencia */
      if (ulItems == 0)
	{
	  if (pChunk)
	    XFree (pChunk);
	  fOk = TRUE;
	  break;
	}

      /* Solo texto de 8 bits */
      if (iFormat != 8)
	{
	  ErrorF ("winClipboardReadIncr - formato %d no soportado\n", iFormat);
	  XFree (pChunk);
	  break;
	}

      ulBytes = ulItems;
      if (ulBytes > g_ulClipboardMaxBytes
	  || ulLen > g_ulClipboardMaxBytes - ulBytes)
	{
	  ErrorF ("winClipboardReadIncr - la selección supera el máximo de "
		  "%lu bytes (-clipboardmaxsize); se descarta\n",
		  g_ulClipboardMaxBytes);
	  XFree (pChunk);
	  break;
	}

      pNew = realloc (pData, ulLen + ulBytes + 1);
      if (pNew == NULL)
	{
	  ErrorF ("winClipboardReadIncr - sin memoria para %lu bytes\n",
		  ulLen + ulBytes + 1);
	  XFree (pChunk);
	  break;
	}
      pData = pNew;
      memcpy (pData + ulLen, pChunk, ulBytes);
      ulLen += ulBytes;
      atomType = atomChunkType;
      XFree (pChunk);
    }

  XSelectInput (pDisplay, iWindow, NoEventMask);

  if (fOk)
    {
      pxtp->value = (unsigned char *) malloc (ulLen + 1);
      if (pxtp->value == NULL)
	fOk = FALSE;
      else
	{
	  if (ulLen)
	    memcpy (pxtp->value, pData, ulLen);
	  pxtp->value[ulLen] = '\0';
	  pxtp->nitems = ulLen;
	  pxtp->encoding = atomType;
	  pxtp->format = 8;
	}
    }

  free (pData);
  return fOk;
}


/*
 * Tamaño a partir del cual hay que enviar con INCR: lo que cabe en una sola
 * petición ChangeProperty (con BIG-REQUESTS, varios MB), con margen para la
 * cabecera de la petición.
 */

unsigned long
winClipboardIncrThreshold (Display *pDisplay)
{
  long lMaxRequest = XExtendedMaxRequestSize (pDisplay);

  if (lMaxRequest <= 0)
    lMaxRequest = XMaxRequestSize (pDisplay);
  return (unsigned long) lMaxRequest * 4 - 1024;
}


/*
 * Entrega pData al cliente que pidió la selección usando INCR, incluido el
 * SelectionNotify. Devuelve FALSE si el cliente no completa la transferencia.
 */

Bool
winClipboardSendIncr (Display *pDisplay, XSelectionRequestEvent *pRequest,
		      Atom atomType, unsigned char *pData, unsigned long ulLen)
{
  Atom			atomIncr = XInternAtom (pDisplay, "INCR", False);
  XSelectionEvent	eventSelection;
  long			lLen = (long) ulLen;
  unsigned long		ulSent = 0;
  Bool			fOk = TRUE;

  /* Avisos de borrado de la propiedad del cliente: piden el siguiente trozo */
  XSelectInput (pDisplay, pRequest->requestor, PropertyChangeMask);

  XChangeProperty (pDisplay, pRequest->requestor, pRequest->property,
		   atomIncr, 32, PropModeReplace, (unsigned char *) &lLen, 1);

  eventSelection.type = SelectionNotify;
  eventSelection.send_event = True;
  eventSelection.display = pDisplay;
  eventSelection.requestor = pRequest->requestor;
  eventSelection.selection = pRequest->selection;
  eventSelection.target = pRequest->target;
  eventSelection.property = pRequest->property;
  eventSelection.time = pRequest->time;
  XSendEvent (pDisplay, pRequest->requestor, False, 0L,
	      (XEvent *) &eventSelection);

  /* Trozos de datos y, al final, uno vacío */
  while (1)
    {
      unsigned long ulChunk = ulLen - ulSent;

      if (ulChunk > WIN_INCR_CHUNK_SIZE)
	ulChunk = WIN_INCR_CHUNK_SIZE;

      if (!winClipboardWaitProperty (pDisplay, pRequest->requestor,
				     pRequest->property, PropertyDelete))
	{
	  ErrorF ("winClipboardSendIncr - el cliente no pidió el siguiente "
		  "trozo (%lu de %lu bytes enviados)\n", ulSent, ulLen);
	  fOk = FALSE;
	  break;
	}

      XChangeProperty (pDisplay, pRequest->requestor, pRequest->property,
		       atomType, 8, PropModeReplace, pData + ulSent,
		       (int) ulChunk);
      XFlush (pDisplay);

      if (ulChunk == 0)
	break;
      ulSent += ulChunk;
    }

  XSelectInput (pDisplay, pRequest->requestor, NoEventMask);
  return fOk;
}
