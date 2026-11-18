/*
 * Copyright (c) 2005 Alexander Gottwald
 *
 * Permission is hereby granted, free of charge, to any person obtaining a
 * copy of this software and associated documentation files (the "Software"),
 * to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense,
 * and/or sell copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE ABOVE LISTED COPYRIGHT HOLDER(S) BE LIABLE FOR ANY CLAIM, DAMAGES OR
 * OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
 * ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
 * DEALINGS IN THE SOFTWARE.
 *
 * Except as contained in this notice, the name(s) of the above copyright
 * holders shall not be used in advertising or otherwise to promote the sale,
 * use or other dealings in this Software without prior written authorization.
 *
 * Authors:	Alexander Gottwald, Colin Harrison
 */
#include <winsock2.h>
#include "window/util.h"
#include "window/wizard.h"
#include "resources/resources.h"
#include "config.h"
#include <prsht.h>
#include <commctrl.h>
#include <htmlhelp.h>
#include <shellapi.h>
#include <shlobj.h>

#include <stdexcept>

/* Puerto TCP del display 0; el display n escucha en 6000 + n */
static const unsigned long X_TCP_PORT = 6000;
static const unsigned long MAX_DISPLAY = 65535 - X_TCP_PORT;
/* Displays que se prueban cuando el campo Display está vacío */
static const unsigned long AUTO_DISPLAYS = 64;

/*
 * Ruta completa entre comillas. CreateProcess(NULL, "ssh ...") busca el
 * ejecutable también en el directorio actual: un ssh.exe o Xming.exe dejado ahí
 * se ejecutaría en su lugar.
 */
static std::wstring QuotePath(const std::wstring &path)
{
    return L"\"" + path + L"\"";
}

static bool FileExists(const std::wstring &path)
{
    DWORD attr = GetFileAttributesW(path.c_str());
    return attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY);
}

/* Carpeta de XLaunch.exe, donde también está Xming.exe */
static std::wstring ModuleDir()
{
    wchar_t buffer[MAX_PATH];
    DWORD len = GetModuleFileNameW(NULL, buffer, MAX_PATH);
    if (len == 0 || len >= MAX_PATH)
        return L"";
    std::wstring path(buffer, len);
    size_t pos = path.find_last_of(L"\\/");
    return pos == std::wstring::npos ? L"" : path.substr(0, pos + 1);
}

/*
 * ssh.exe del OpenSSH integrado en Windows 10/11, o cadena vacía. XLaunch es de
 * 32 bits: en un Windows de 64 bits, System32 se redirige a SysWOW64 (donde no
 * está OpenSSH), así que primero se prueba Sysnative.
 */
static std::wstring FindWindowsOpenSSH()
{
    wchar_t windir[MAX_PATH];
    UINT len = GetSystemWindowsDirectoryW(windir, MAX_PATH);
    if (len == 0 || len >= MAX_PATH)
        return L"";
    std::wstring dir(windir);
    const wchar_t *subdirs[] = { L"\\Sysnative\\OpenSSH\\ssh.exe", L"\\System32\\OpenSSH\\ssh.exe" };
    for (size_t i = 0; i < sizeof(subdirs) / sizeof(subdirs[0]); i++)
        if (FileExists(dir + subdirs[i]))
            return dir + subdirs[i];
    return L"";
}

std::wstring FilePath (HWND hwnd, bool PuTTY);
BOOL FileRead (LPCWSTR lpstrFileName);

/*
 * Un argumento entre comillas según las reglas de CommandLineToArgvW: las
 * comillas internas se escapan y las barras invertidas que las preceden se
 * duplican. Antes la contraseña de plink iba sin comillas: una con espacios
 * partía la línea de comandos.
 */
static std::wstring QuoteArg(const std::wstring &arg)
{
    std::wstring out = L"\"";
    size_t slashes = 0;
    for (size_t i = 0; i < arg.size(); i++)
    {
        if (arg[i] == L'\\')
        {
            slashes++;
            continue;
        }
        if (arg[i] == L'"')
            out.append(slashes * 2 + 1, L'\\');
        else
            out.append(slashes, L'\\');
        slashes = 0;
        out += arg[i];
    }
    out.append(slashes * 2, L'\\');
    return out + L"\"";
}

/* Número de display válido: solo dígitos y puerto TCP dentro de rango */
static bool ValidDisplay(const std::wstring &display)
{
    if (display.empty() || display.size() > 5)
        return false;
    for (size_t i = 0; i < display.size(); i++)
        if (display[i] < L'0' || display[i] > L'9')
            return false;
    return wcstoul(display.c_str(), NULL, 10) <= MAX_DISPLAY;
}

/*
 * ¿Hay un servidor escuchando en 127.0.0.1:6000+n? Sustituye a XOpenDisplay:
 * XLaunch ya no enlaza libX11 ni deja abierta una conexión X que nunca cerraba.
 */
static bool DisplayListening(unsigned long display)
{
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET)
        return false;
    sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons((u_short)(X_TCP_PORT + display));
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    bool listening = connect(s, (sockaddr *)&addr, sizeof(addr)) == 0;
    closesocket(s);
    return listening;
}

/* Primer display libre (campo Display vacío) */
static std::wstring FreeDisplay()
{
    for (unsigned long n = 0; n < AUTO_DISPLAYS; n++)
        if (!DisplayListening(n))
        {
            wchar_t buffer[16];
            swprintf(buffer, sizeof(buffer) / sizeof(buffer[0]), L"%lu", n);
            return buffer;
        }
    return L"";
}

static std::wstring KnownFolder(int csidl)
{
    wchar_t buffer[MAX_PATH];
    if (SHGetFolderPathW(NULL, csidl, NULL, SHGFP_TYPE_CURRENT, buffer) != S_OK)
        return L"";
    return std::wstring(buffer) + L"\\";
}

/*
 * Fichero .xlaunch de -load/-run/-validate. Si no existe tal cual y es un nombre
 * relativo, se busca (con y sin la extensión .xlaunch) en %APPDATA%\Xming, el
 * Escritorio, el perfil del usuario y la carpeta de XLaunch.
 */
static std::wstring FindConfigFile(const std::wstring &name)
{
    if (FileRead(name.c_str()))
        return name;
    bool relative = name.find(L':') == std::wstring::npos
        && !name.empty() && name[0] != L'\\' && name[0] != L'/';
    if (!relative)
        return name;
    std::wstring dirs[4] = {
        KnownFolder(CSIDL_APPDATA) + L"Xming\\",
        KnownFolder(CSIDL_DESKTOPDIRECTORY),
        KnownFolder(CSIDL_PROFILE),
        ModuleDir(),
    };
    std::wstring names[2] = { name, name + L".xlaunch" };
    for (size_t d = 0; d < 4; d++)
        for (size_t n = 0; n < 2; n++)
            if (dirs[d].size() > 1 && FileRead((dirs[d] + names[n]).c_str()))
                return dirs[d] + names[n];
    return name;
}

static int MessageFromResources(HWND hwnd, UINT message, UINT caption, UINT type,
                                LPCWSTR detail = NULL)
{
    wchar_t szMessage[1024];
    wchar_t szCaption[MAX_CAPTION];
    HINSTANCE hInst = GetModuleHandle(NULL);
    LoadStringW(hInst, caption, szCaption, sizeof(szCaption) / sizeof(wchar_t));
    if (message)
        LoadStringW(hInst, message, szMessage, sizeof(szMessage) / sizeof(wchar_t));
    std::wstring text = message ? szMessage : L"";
    if (detail)
        text = text.empty() ? std::wstring(detail) : text + L"\n\n" + detail;
    return MessageBoxW(hwnd, text.c_str(), szCaption, type);
}

bool stripspace(wchar_t *s, wchar_t *t)
{
    bool strip = false;
    while (*t == L' ') {
	strip = true;
	*t++;
    }
    while (*t != L'\0') {
	if (*t == L'.' || *t == L'-' || *t == L'_');
	else if (*t == L' ' || !iswalnum(*t)) {
	   strip = true;
	   break;
	}
	*s++ = *t++;
    }
    *s = L'\0';
    return strip;
}

/// @brief Actual wizard implementation.
/// This is based on generic CWizard but handles the special dialogs
class CMyWizard : public CWizard 
{
    public:
    private:
	CConfig config; /// Storage for config options.
	bool passwordMode;
    public:
        /// @brief Constructor.
        /// Set wizard pages.
        CMyWizard() : CWizard() 
        {
    	    passwordMode = false;

            AddPage(IDD_DISPLAY, IDS_DISPLAY_TITLE, IDS_DISPLAY_SUBTITLE);
            AddPage(IDD_CLIENTS, IDS_CLIENTS_TITLE, IDS_CLIENTS_SUBTITLE);
            AddPage(IDD_PROGRAM, IDS_PROGRAM_TITLE, IDS_PROGRAM_SUBTITLE);
            AddPage(IDD_XDMCP, IDS_XDMCP_TITLE, IDS_XDMCP_SUBTITLE);
            AddPage(IDD_CLIPBOARD, IDS_CLIPBOARD_TITLE, IDS_CLIPBOARD_SUBTITLE);
            AddPage(IDD_FINISH, IDS_FINISH_TITLE, IDS_FINISH_SUBTITLE);
        }
        
        virtual void InitPasswordMode()
        {
    	    passwordMode = true;

	    ClearPages();
	    AddPage(IDD_PROGRAM, IDS_PASSWORD_TITLE, IDS_PASSWORD_SUBTITLE);
        }

	virtual void LoadConfig(LPCWSTR filename, bool validate)
	{
	    try {
		config.Load(filename, validate);
	    } catch (std::runtime_error &e)
	    {
		printf("Error: %s\n", e.what());
	    }
	}

	virtual void StripStart()
	{
	    wchar_t *pwchar;
	    wchar_t buffer[256];
	    if (!config.user.empty())
	    {
		pwchar = (wchar_t*)config.user.c_str();
		if (stripspace(buffer, pwchar)) config.user = buffer;
	    }
	    if (!config.host.empty())
	    {
		pwchar = (wchar_t*)config.host.c_str();
		if (stripspace(buffer, pwchar)) config.host = buffer;
	    }
	    if (!config.xdmcp_host.empty())
	    {
		pwchar = (wchar_t*)config.xdmcp_host.c_str();
		if (stripspace(buffer, pwchar)) config.xdmcp_host = buffer;
	    }
	    if (!config.font_server.empty())
	    {
		pwchar = (wchar_t*)config.font_server.c_str();
		if (stripspace(buffer, pwchar)) config.font_server = buffer;
	    }
	}

	virtual BOOL PasswordStart()
	{
	    if (config.password_start && config.password.empty()) return TRUE;
	    return FALSE;
	}

	virtual BOOL PasswordStartPopulated()
	{
	    if (config.client != CConfig::StartProgram || config.clientstart != CConfig::PuTTY ||
		config.program.empty() || config.host.empty()) return FALSE;
	    return TRUE;
	}

	virtual BOOL StartPopulated()
	{
	    if (config.client == CConfig::StartProgram)
	    {
		if (config.clientstart == CConfig::Local)
		{
			if (config.program.empty()) return FALSE;
		}
		else if (config.clientstart == CConfig::PuTTY || config.clientstart == CConfig::OpenSSH)
		{
			if (config.program.empty() || config.host.empty()) return FALSE;
		}
		else return FALSE;
	    }
	    if (config.client == CConfig::XDMCP)
	    {
			if (!config.broadcast && config.xdmcp_host.empty()) return FALSE;
	    }
	    return TRUE;
	}

        /// @brief Handle the PSN_WIZNEXT message.
        /// @param hwndDlg Handle to active page dialog.
        /// @param index Index of current page.
        /// @return TRUE if the message was handled. FALSE otherwise. 
	virtual BOOL WizardNext(HWND hwndDlg, unsigned index)
	{
#ifdef _DEBUG
	    printf("%s %d\n", __FUNCTION__, index);
#endif
	    switch (PageID(index))
	    {
		case IDD_DISPLAY:
                    // Check for select window mode
		    if (IsDlgButtonChecked(hwndDlg, IDC_MULTIWINDOW))
			config.window = CConfig::MultiWindow;
		    else if (IsDlgButtonChecked(hwndDlg, IDC_FULLSCREEN))
			config.window = CConfig::Fullscreen;
		    else if (IsDlgButtonChecked(hwndDlg, IDC_WINDOWED))
			config.window = CConfig::Windowed;
		    else if (IsDlgButtonChecked(hwndDlg, IDC_NODECORATION))
			config.window = CConfig::Nodecoration;
		    else
		    {
			SetWindowLong(hwndDlg, DWL_MSGRESULT, -1);
			return TRUE;
		    }
                    // Get selected display number
		    {
			wchar_t buffer[512];
			GetDlgItemTextW(hwndDlg, IDC_DISPLAY, buffer, 512);
			buffer[511] = L'\0';
			config.display = buffer;
                    }
                    // Vacío: el primer display libre al arrancar
                    if (!config.display.empty() && !ValidDisplay(config.display))
		    {
			MessageFromResources(hwndDlg, IDS_BAD_DISPLAY_MESS, IDS_BAD_DISPLAY_CAP,
					     MB_OK | MB_ICONEXCLAMATION);
			SetWindowLong(hwndDlg, DWL_MSGRESULT, -1);
		    }
                    else
                        SetWindowLong(hwndDlg, DWL_MSGRESULT, IDD_CLIENTS);
		    return TRUE;
		case IDD_CLIENTS:
                    // Check for select client startup method
		    if (IsDlgButtonChecked(hwndDlg, IDC_CLIENT))
		    {
			config.client = CConfig::StartProgram;
			SetWindowLong(hwndDlg, DWL_MSGRESULT, IDD_PROGRAM);
		    } else if (IsDlgButtonChecked(hwndDlg, IDC_XDMCP))
		    {
			config.client = CConfig::XDMCP;
			SetWindowLong(hwndDlg, DWL_MSGRESULT, IDD_XDMCP);
		    } else if (IsDlgButtonChecked(hwndDlg, IDC_CLIENT_NONE))
		    {
			config.client = CConfig::NoClient;
			SetWindowLong(hwndDlg, DWL_MSGRESULT, IDD_CLIPBOARD);
		    } else
			SetWindowLong(hwndDlg, DWL_MSGRESULT, -1);
		    return TRUE;
		case IDD_PROGRAM:
                    // Read program, user and host name
		    {
			bool strip = false;
			wchar_t buffer[512];
			GetDlgItemTextW(hwndDlg, IDC_CLIENT_PASSWORD, buffer, 512);
			config.password = buffer;
			if (config.password.empty())
				config.password_start = false;
			else
				config.password_start = true;
			GetDlgItemTextW(hwndDlg, IDC_CLIENT_USER, buffer, 512);
			buffer[511] = L'\0';
			if (stripspace(buffer, buffer))
			{
				SetDlgItemTextW(hwndDlg, IDC_CLIENT_USER, buffer);
				strip = true;
			}
			config.user = buffer;
			GetDlgItemTextW(hwndDlg, IDC_CLIENT_HOST, buffer, 512);
			buffer[511] = L'\0';
			if (stripspace(buffer, buffer))
			{
				SetDlgItemTextW(hwndDlg, IDC_CLIENT_HOST, buffer);
				strip = true;
			}
			config.host = buffer;
			GetDlgItemTextW(hwndDlg, IDC_CLIENT_PROGRAM, buffer, 512);
			buffer[511] = L'\0';
			config.program = buffer;
			if (strip)
			{
				SetWindowLong(hwndDlg, DWL_MSGRESULT, -1);
				return TRUE;
			}
		    }
		    if (IsDlgButtonChecked(hwndDlg, IDC_COMPRESS))
			config.compress = true;
		    else
			config.compress = false;
                    // Check local or remote client
		    if (IsDlgButtonChecked(hwndDlg, IDC_CLIENT_LOCAL))
			config.clientstart = CConfig::Local;
		    else
		    {
			int reads = 0;
			BOOL puttyset = IsDlgButtonChecked(hwndDlg, IDC_CLIENT_REMOTE_PUTTY);
			if (!puttyset && config.protocol_path.empty() && !FindWindowsOpenSSH().empty())
			    reads = 2;  // ssh.exe del sistema encontrado: no preguntar
			wchar_t buffer[MAX_PATH];
			for (reads = 0; reads < 2; reads++)
			{
			    buffer[0] = L'\0';
			    if (!config.protocol_path.empty()) wcscpy (buffer, config.protocol_path.c_str());
			    if (puttyset) wcscat(buffer, L"plink.exe");
			    else wcscat(buffer, L"ssh.exe");
			    if (!FileRead(buffer))
			    {
				if (reads < 1) config.protocol_path = FilePath(hwndDlg, puttyset);
				else
				{
					SetWindowLong(hwndDlg, DWL_MSGRESULT, -1);
					return TRUE;
				}
			    }
			}
			if (puttyset) config.clientstart = CConfig::PuTTY;
			else config.clientstart = CConfig::OpenSSH;
		    }
                    // Check for valid input
		    if ((config.clientstart != CConfig::Local) && (config.host.empty() || config.program.empty()))
			SetWindowLong(hwndDlg, DWL_MSGRESULT, -1);
		    else
			SetWindowLong(hwndDlg, DWL_MSGRESULT, IDD_CLIPBOARD);
		    return TRUE;
		case IDD_XDMCP:
                    // Check for broadcast
		    if (IsDlgButtonChecked(hwndDlg, IDC_XDMCP_BROADCAST))
			config.broadcast = true;
		    else if (IsDlgButtonChecked(hwndDlg, IDC_XDMCP_QUERY))
			config.broadcast = false;
		    else
		    {
			SetWindowLong(hwndDlg, DWL_MSGRESULT, -1);
			return TRUE;
		    }
                    // Check for indirect mode
		    if (IsDlgButtonChecked(hwndDlg, IDC_XDMCP_INDIRECT))
			config.indirect = true;
		    else
			config.indirect = false;
                    // Read hostname
		    {
			wchar_t buffer[512];
			GetDlgItemTextW(hwndDlg, IDC_XDMCP_HOST, buffer, 512);
			buffer[511] = L'\0';
			if (stripspace(buffer, buffer))
			{
				SetDlgItemTextW(hwndDlg, IDC_XDMCP_HOST, buffer);
				SetWindowLong(hwndDlg, DWL_MSGRESULT, -1);
				return TRUE;
			}
			config.xdmcp_host = buffer;
		    }
                    // Check for valid input
		    if (!config.broadcast && config.xdmcp_host.empty())
			SetWindowLong(hwndDlg, DWL_MSGRESULT, -1);
		    else	
			SetWindowLong(hwndDlg, DWL_MSGRESULT, IDD_CLIPBOARD);
		    return TRUE;
                case IDD_CLIPBOARD:
                    // check for clipboard
                    if (IsDlgButtonChecked(hwndDlg, IDC_CLIPBOARD))
                        config.clipboard = true;
                    else
                        config.clipboard = false;
		    // check for access control
		    if (IsDlgButtonChecked(hwndDlg, IDC_NO_ACCESS_CONTROL))
		    {
			// -ac abre el servidor a cualquier equipo de la red: confirmarlo
			if (!config.no_access_control
			    && MessageFromResources(hwndDlg, IDS_NOAC_MESS, IDS_NOAC_CAP,
						    MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2) != IDYES)
			{
			    CheckDlgButton(hwndDlg, IDC_NO_ACCESS_CONTROL, BST_UNCHECKED);
			    SetWindowLong(hwndDlg, DWL_MSGRESULT, -1);
			    return TRUE;
			}
			config.no_access_control = true;
		    }
		    else
			config.no_access_control = false;
                    // read parameters
		    {
			wchar_t buffer[512];
                        GetDlgItemTextW(hwndDlg, IDC_FONT_SERVER, buffer, 512);
                        buffer[511] = L'\0';
			if (stripspace(buffer, buffer))
			{
				SetDlgItemTextW(hwndDlg, IDC_FONT_SERVER, buffer);
				SetWindowLong(hwndDlg, DWL_MSGRESULT, -1);
				return TRUE;
			}
			config.font_server = buffer;
			GetDlgItemTextW(hwndDlg, IDC_EXTRA_PARAMS, buffer, 512);
			buffer[511] = L'\0';
			config.extra_params = buffer;
			GetDlgItemTextW(hwndDlg, IDC_EXTRA_SSH, buffer, 512);
			buffer[511] = L'\0';
			config.extra_ssh = buffer;
		    }
                    SetWindowLong(hwndDlg, DWL_MSGRESULT, IDD_FINISH);
                    return TRUE;
		default:
		    break;
	    }
	    return FALSE;
	}
        /// @brief Handle PSN_WIZFINISH message.
        /// @param hwndDlg Handle to active page dialog.
        /// @param index Index of current page.
        /// @return TRUE if the message was handled. FALSE otherwise. 
	virtual BOOL WizardFinish(HWND hwndDlg, unsigned index)
	{
#ifdef _DEBUG
	    printf("finish %d\n", index);
#endif
	    if (passwordMode)
		switch (PageID(index))
		{
		    case IDD_PROGRAM:
                	// Read program, user and host name
			{
			    wchar_t buffer[512];
			    GetDlgItemTextW(hwndDlg, IDC_CLIENT_PASSWORD, buffer, 512);
			    buffer[511] = L'\0';
			    config.password = buffer;
			    if (config.password.empty())
				config.password_start = false;
			    else
				config.password_start = true;
			}
			return TRUE;
		    default:
			break;
		}
	    return FALSE;
	}
        /// @brief Handle PSN_WIZBACK message.
        /// Basicly handles switching to proper page (skipping XDMCP or program page
        /// if required).
        /// @param hwndDlg Handle to active page dialog.
        /// @param index Index of current page.
        /// @return TRUE if the message was handled. FALSE otherwise. 
	virtual BOOL WizardBack(HWND hwndDlg, unsigned index)
	{
	    switch (PageID(index))
	    {
		case IDD_PROGRAM:
		case IDD_XDMCP:
		    SetWindowLong(hwndDlg, DWL_MSGRESULT, IDD_CLIENTS);
		    return TRUE;
                case IDD_CLIPBOARD:
		    switch (config.client)
		    {
			case CConfig::NoClient:	
			    SetWindowLong(hwndDlg, DWL_MSGRESULT, IDD_CLIENTS);
			    return TRUE;
			case CConfig::StartProgram:
			    SetWindowLong(hwndDlg, DWL_MSGRESULT, IDD_PROGRAM);
			    return TRUE;
			case CConfig::XDMCP:
			    SetWindowLong(hwndDlg, DWL_MSGRESULT, IDD_XDMCP);
			    return TRUE;
		    }
		    break;
	    }
	    return FALSE;
	}
        /// @brief Handle PSN_SETACTIVE message.
        /// @param hwndDlg Handle to active page dialog.
        /// @param index Index of current page.
        /// @return TRUE if the message was handled. FALSE otherwise. 
	virtual BOOL WizardActivate(HWND hwndDlg, unsigned index)
	{
#ifdef _DEBUG
	    printf("%s %d\n", __FUNCTION__, index);
#endif
	    switch (PageID(index))
	    {
		case IDD_CLIENTS:
                    // Enable or disable XDMCP radiobutton and text
		    EnableWindow(GetDlgItem(hwndDlg, IDC_XDMCP), config.window != CConfig::MultiWindow);
		    EnableWindow(GetDlgItem(hwndDlg, IDC_XDMCP_DESC), config.window != CConfig::MultiWindow);
		    break;
	    }
	    return FALSE;
	}
	/// @brief Handle F1 and PSN_HELP message.
	/// @param hwndDlg Handle to active page dialog.
	/// @param index Index of current page.
	virtual void WizardHelp(HWND hwndDlg, unsigned index)
	{
#ifdef _DEBUG
	    printf("%s %d\n", __FUNCTION__, index);
#endif
	    int offset = 0;
	    int idd = PageID(index);
	    if (idd==IDD_DISPLAY) offset = 0;
	    else if (idd==IDD_CLIENTS) offset = 1;
	    else if (idd==IDD_PROGRAM) offset = 2;
	    else if (idd==IDD_XDMCP) offset = 3;
	    else if (idd==IDD_CLIPBOARD) offset = 4;
	    else if (idd==IDD_FINISH) offset = 5;
	    // La ayuda XLaunch.chm de Xming no es redistribuible y no se incluye:
	    // sin ella se muestra un resumen de la página en lugar de nada.
	    std::wstring chm = ModuleDir() + L"XLaunch.chm";
	    if (FileExists(chm) && HtmlHelpW(hwndDlg, chm.c_str(), HH_HELP_CONTEXT, 500 + offset))
		return;
	    MessageFromResources(hwndDlg, IDS_HELP_DISPLAY + offset, IDS_HELP_CAP,
				 MB_OK | MB_ICONINFORMATION);
	}

    protected:
        /// @brief Enable or disable the control for remote clients.
        /// @param hwndDlg Handle to active page dialog.
        /// @param state State of control group.
	void EnableRemoteProgramGroup(HWND hwndDlg, BOOL state)
	{
	    EnableWindow(GetDlgItem(hwndDlg, IDC_COMPRESS), state);
	    EnableWindow(GetDlgItem(hwndDlg, IDC_CLIENT_HOST), state);
	    EnableWindow(GetDlgItem(hwndDlg, IDC_CLIENT_USER), state);
	    EnableWindow(GetDlgItem(hwndDlg, IDC_CLIENT_HOST_DESC), state);
	    EnableWindow(GetDlgItem(hwndDlg, IDC_CLIENT_USER_DESC), state);
	}
	void EnableRemotePassword(HWND hwndDlg, BOOL state)
	{
	    EnableWindow(GetDlgItem(hwndDlg, IDC_CLIENT_PASSWORD), state);
	    EnableWindow(GetDlgItem(hwndDlg, IDC_CLIENT_PASSWORD_DESC), state);
	}
	void EnableLocalRemoteGroup(HWND hwndDlg, BOOL state)
	{
	    EnableWindow(GetDlgItem(hwndDlg, IDC_CLIENT_PROGRAM), state);
	    EnableWindow(GetDlgItem(hwndDlg, IDC_CLIENT_PROGRAM_DESC), state);
	    EnableWindow(GetDlgItem(hwndDlg, IDC_CLIENT_LOCAL), state);
	    EnableWindow(GetDlgItem(hwndDlg, IDC_CLIENT_REMOTE_PUTTY), state);
	    EnableWindow(GetDlgItem(hwndDlg, IDC_CLIENT_REMOTE_SSH), state);
	}
        /// @brief Enable or disable the control for XDMCP connection.
        /// @param hwndDlg Handle to active page dialog.
        /// @param state State of control group.
	void EnableXDMCPQueryGroup(HWND hwndDlg, BOOL state)
	{
	    EnableWindow(GetDlgItem(hwndDlg, IDC_XDMCP_HOST), state);
	    EnableWindow(GetDlgItem(hwndDlg, IDC_XDMCP_INDIRECT), state);
	}
	/// @brief Enable or disable the control for no access control.
	/// @param hwndDlg Handle to active page dialog.
	/// @param state State of control group.
	void EnableNoAccessControlGroup(HWND hwndDlg, BOOL state)
	{
	    EnableWindow(GetDlgItem(hwndDlg, IDC_NO_ACCESS_CONTROL), state);
	    EnableWindow(GetDlgItem(hwndDlg, IDC_NO_ACCESS_CONTROL_DESC), state);
	}
	/// @brief Enable or disable the control for SSH extras.
	/// @param hwndDlg Handle to active page dialog.
	/// @param state State of control group.
	void EnableSSHExtrasGroup(HWND hwndDlg, BOOL state)
	{
	    EnableWindow(GetDlgItem(hwndDlg, IDC_EXTRA_SSH), state);
	    EnableWindow(GetDlgItem(hwndDlg, IDC_EXTRA_SSH_DESC), state);
	}
        /// @brief Fill program box with default values.
        /// @param hwndDlg Handle to active page dialog.
	void FillProgramBox(HWND hwndDlg)
	{
	    HWND cbwnd = GetDlgItem(hwndDlg, IDC_CLIENT_PROGRAM);
	    if (cbwnd == NULL)
		return;
	    SendMessage(cbwnd, CB_RESETCONTENT, 0, 0);
	    for (int i = 0; i < PROG_NUMBER; i++)
		if (!config.progs[i].empty())
			SendMessageW(cbwnd, CB_ADDSTRING, 0, (LPARAM)config.progs[i].c_str());
	    SendMessage(cbwnd, CB_SETCURSEL, 0, 0);
	}
	// Devuelve la ruta guardada o una cadena vacía. Antes devolvía un puntero al
	// búfer local del diálogo, que ya no existía al usarlo.
	std::wstring ShowSaveDialog(HWND parent, LPCWSTR filename)
	{
	    wchar_t szTitle[512];
	    wchar_t szFilter[512];
	    wchar_t szFileTitle[512];
	    wchar_t szFile[MAX_PATH];
	    HINSTANCE hInst = GetModuleHandle(NULL);
	    
	    LoadStringW(hInst, IDS_SAVE_TITLE, szTitle, sizeof(szTitle)/sizeof(wchar_t));
	    LoadStringW(hInst, IDS_SAVE_FILETITLE, szFileTitle, sizeof(szFileTitle)/sizeof(wchar_t));
	    LoadStringW(hInst, IDS_SAVE_FILTER, szFilter, sizeof(szFilter)/sizeof(wchar_t));
	    for (unsigned i=0; szFilter[i]; i++) 
		if (szFilter[i] == L'%') 
		    szFilter[i] = L'\0'; 

	    wcscpy(szFile, filename);

	    OPENFILENAMEW ofn;
	    memset(&ofn, 0, sizeof(OPENFILENAMEW));
	    ofn.lStructSize = sizeof(OPENFILENAMEW); 
	    ofn.hwndOwner = parent; 
	    ofn.lpstrFilter = szFilter; 
	    ofn.lpstrFile= szFile; 
	    ofn.nMaxFile = sizeof(szFile)/ sizeof(*szFile); 
	    ofn.lpstrFileTitle = szFileTitle;
	    ofn.nMaxFileTitle = sizeof(szFileTitle) / sizeof(*szFileTitle);
	    ofn.lpstrInitialDir = NULL;
	    ofn.lpstrDefExt = L"xlaunch";	// añade .xlaunch si el nombre no lleva extensión
	    ofn.Flags = OFN_OVERWRITEPROMPT | OFN_PATHMUSTEXIST;
	    ofn.lpstrTitle = szTitle;

	    if (GetSaveFileNameW(&ofn))
	    {
		try {
      		    config.Save(ofn.lpstrFile, false);
		} catch (std::runtime_error &e)
		{
		    printf("Error: %s\n", e.what());
		}
		return ofn.lpstrFile;
	    }
	    return L"";
	}
    public:
	   
        /// @brief Handle messages fo the dialog pages.
        /// @param hwndDlg Handle of active dialog.
        /// @param uMsg Message code.
        /// @param wParam Message parameter.
        /// @param lParam Message parameter.
        /// @param psp Handle to sheet paramters. 
        virtual INT_PTR PageDispatch(HWND hwndDlg, UINT uMsg, WPARAM wParam, LPARAM lParam, PROPSHEETPAGEW *psp)
        {
            HWND hwnd;
            switch (uMsg)
            {
                case WM_INITDIALOG:
                    switch (PageID(PageIndex(psp)))
                    {
                        case IDD_DISPLAY:
			    psp->dwFlags |= PSP_HASHELP;
                            // Init display dialog. Enable correct check buttons
			    switch (config.window)
			    {
				default:
				case CConfig::MultiWindow:
				    CheckRadioButton(hwndDlg, IDC_MULTIWINDOW, IDC_NODECORATION, IDC_MULTIWINDOW);
				    break;
				case  CConfig::Fullscreen:
				    CheckRadioButton(hwndDlg, IDC_MULTIWINDOW, IDC_NODECORATION, IDC_FULLSCREEN);
				    break;
				case  CConfig::Windowed:
				    CheckRadioButton(hwndDlg, IDC_MULTIWINDOW, IDC_NODECORATION, IDC_WINDOWED);
				    break;
				case  CConfig::Nodecoration:
				    CheckRadioButton(hwndDlg, IDC_MULTIWINDOW, IDC_NODECORATION, IDC_NODECORATION);
				    break;
			    }
                            // Set display number
                            SetDlgItemTextW(hwndDlg, IDC_DISPLAY, config.display.c_str());
                            break;
                        case IDD_CLIENTS:
			    psp->dwFlags |= PSP_HASHELP;
                            // Init client dialog. Enable correct check buttons
			    switch (config.client)
			    {
				default:
				case CConfig::NoClient:
				    CheckRadioButton(hwndDlg, IDC_CLIENT_NONE, IDC_CLIENT, IDC_CLIENT_NONE);
				    break;
				case CConfig::StartProgram:
				    CheckRadioButton(hwndDlg, IDC_CLIENT_NONE, IDC_CLIENT, IDC_CLIENT);
				    break;
				case CConfig::XDMCP:
				    CheckRadioButton(hwndDlg, IDC_CLIENT_NONE, IDC_CLIENT, IDC_XDMCP);
				    break;
			    }
                            break;
			case IDD_PROGRAM:
			    psp->dwFlags |= PSP_HASHELP;
                           // Init start dialog. Enable correct check buttons
			    switch (config.clientstart)
 			    {
				default:
				case CConfig::Local:
				    CheckRadioButton(hwndDlg, IDC_CLIENT_LOCAL, IDC_CLIENT_REMOTE_SSH, IDC_CLIENT_LOCAL);
				    EnableRemotePassword(hwndDlg, false);
				    EnableRemoteProgramGroup(hwndDlg, false);
				    break;
				case CConfig::PuTTY:
				    CheckRadioButton(hwndDlg, IDC_CLIENT_LOCAL, IDC_CLIENT_REMOTE_SSH, IDC_CLIENT_REMOTE_PUTTY);
				    EnableRemotePassword(hwndDlg, true);
				    EnableRemoteProgramGroup(hwndDlg, true);
				    break;
				case CConfig::OpenSSH:
				    CheckRadioButton(hwndDlg, IDC_CLIENT_LOCAL, IDC_CLIENT_REMOTE_SSH, IDC_CLIENT_REMOTE_SSH);
				    EnableRemotePassword(hwndDlg, false);
				    EnableRemoteProgramGroup(hwndDlg, true);
				    break;
                            }
                            // Fill combo boxes
			    FillProgramBox(hwndDlg);
                            // Set edit fields
			    if (!config.program.empty())
			       	SetDlgItemTextW(hwndDlg, IDC_CLIENT_PROGRAM, config.program.c_str());
			    SetDlgItemTextW(hwndDlg, IDC_CLIENT_HOST, config.host.c_str());
			    SetDlgItemTextW(hwndDlg, IDC_CLIENT_USER, config.user.c_str());
			    SetDlgItemTextW(hwndDlg, IDC_CLIENT_PASSWORD, config.password.c_str());
			    CheckDlgButton(hwndDlg, IDC_COMPRESS, config.compress?BST_CHECKED:BST_UNCHECKED);

			    if (passwordMode)
			    {
				wchar_t szDesc[64];
			        EnableLocalRemoteGroup(hwndDlg, false);
			        EnableRemoteProgramGroup(hwndDlg, false);
			        EnableRemotePassword(hwndDlg, true);

				LoadStringW(GetModuleHandle(NULL), IDS_REENTER_PASS, szDesc, sizeof(szDesc)/sizeof(wchar_t));
			        SetDlgItemTextW(hwndDlg, IDC_CLIENT_PASSWORD_DESC, szDesc);
			    }
			    break;
			case IDD_XDMCP:
			    psp->dwFlags |= PSP_HASHELP;
                            // Init XDMCP dialog. Check broadcast and indirect button
                            CheckRadioButton(hwndDlg, IDC_XDMCP_QUERY, IDC_XDMCP_BROADCAST, config.broadcast?IDC_XDMCP_BROADCAST:IDC_XDMCP_QUERY);
                            CheckDlgButton(hwndDlg, IDC_XDMCP_INDIRECT, config.indirect?BST_CHECKED:BST_UNCHECKED);
			    EnableXDMCPQueryGroup(hwndDlg, config.broadcast?FALSE:TRUE);
                            // Set hostname
			    SetDlgItemTextW(hwndDlg, IDC_XDMCP_HOST, config.xdmcp_host.c_str());
			    break;
                        case IDD_CLIPBOARD:
			    psp->dwFlags |= PSP_HASHELP;
                            CheckDlgButton(hwndDlg, IDC_CLIPBOARD, config.clipboard?BST_CHECKED:BST_UNCHECKED);
			    CheckDlgButton(hwndDlg, IDC_NO_ACCESS_CONTROL, config.no_access_control?BST_CHECKED:BST_UNCHECKED);
                            SetDlgItemTextW(hwndDlg, IDC_FONT_SERVER, config.font_server.c_str());
                            SetDlgItemTextW(hwndDlg, IDC_EXTRA_PARAMS, config.extra_params.c_str());
                            SetDlgItemTextW(hwndDlg, IDC_EXTRA_SSH, config.extra_ssh.c_str());
                            break;
			case IDD_FINISH:
			    psp->dwFlags |= PSP_HASHELP;
			    break;

                    }
		case WM_NOTIFY:
		  {
		    LPNMHDR lpnm = (LPNMHDR) lParam;
		    if (lpnm->code == PSN_SETACTIVE)
		    {
			switch (PageID(PageIndex(psp)))
			{
			    case IDD_CLIENTS:
				if (config.window == CConfig::MultiWindow && IsDlgButtonChecked(hwndDlg, IDC_XDMCP))
				{
				    CheckDlgButton(hwndDlg, IDC_XDMCP, BST_UNCHECKED);
				    CheckDlgButton(hwndDlg, IDC_CLIENT_NONE, BST_CHECKED);
				}
				break;
			    case IDD_CLIPBOARD:
				if (config.client == CConfig::XDMCP || config.clientstart == CConfig::PuTTY || config.clientstart == CConfig::OpenSSH)
				{
				    CheckDlgButton(hwndDlg, IDC_NO_ACCESS_CONTROL, BST_UNCHECKED);
				    EnableNoAccessControlGroup(hwndDlg, false);
				}
				else
				    EnableNoAccessControlGroup(hwndDlg, true);
				if (config.clientstart ==  CConfig::PuTTY || config.clientstart ==  CConfig::OpenSSH)
				    EnableSSHExtrasGroup(hwndDlg, true);
				else EnableSSHExtrasGroup(hwndDlg, false);
				break;
			    case IDD_FINISH:
				if (config.clientstart == CConfig::PuTTY && !config.password.empty())
				    EnableWindow(GetDlgItem(hwndDlg, IDC_SAVEPASSWORD), true);
				else
				{
				    CheckDlgButton(hwndDlg, IDC_SAVEPASSWORD, BST_UNCHECKED);
				    EnableWindow(GetDlgItem(hwndDlg, IDC_SAVEPASSWORD), false);
				}
				break;
			}
		    }
		  }
		    break;
                case WM_COMMAND:
                    // Handle control messages
                    switch (LOWORD(wParam))
                    {
                        // Handle clicks on images. Check proper radiobutton
                        case IDC_MULTIWINDOW_IMG:
                        case IDC_FULLSCREEN_IMG:
                        case IDC_WINDOWED_IMG:
                        case IDC_NODECORATION_IMG:
                            CheckRadioButton(hwndDlg, IDC_MULTIWINDOW, IDC_NODECORATION, LOWORD(wParam)-4);
                            SetFocus(GetDlgItem(hwndDlg, LOWORD(wParam)-4));
                            break;
                        // Disable unavailable controls 
			case IDC_CLIENT_REMOTE_SSH:
			    EnableRemotePassword(hwndDlg, false);
			    EnableRemoteProgramGroup(hwndDlg, true);
			    break;
                        case IDC_CLIENT_REMOTE_PUTTY:
			    EnableRemotePassword(hwndDlg, true);
			    EnableRemoteProgramGroup(hwndDlg, true);
			    break;
                        case IDC_CLIENT_LOCAL:
			    EnableRemotePassword(hwndDlg, false);
			    EnableRemoteProgramGroup(hwndDlg, false);
                            break;
			case IDC_XDMCP_QUERY:
			case IDC_XDMCP_BROADCAST:
			    EnableXDMCPQueryGroup(hwndDlg, LOWORD(wParam) == IDC_XDMCP_QUERY);
			    break;
			case IDC_FINISH_SAVE:
			    // check for save password
			    if (IsDlgButtonChecked(hwndDlg, IDC_SAVEPASSWORD))
				config.password_save = true;
			    else
				config.password_save = false;
			    {
				wchar_t szCaption[MAX_CAPTION];
				std::wstring filename = ShowSaveDialog(hwndDlg, L"config.xlaunch");
				if (filename.empty()) break;
			    	if (!FileRead(filename.c_str())) {
				    LoadStringW(GetModuleHandle(NULL), IDS_CANNOT_OPEN, szCaption, sizeof(szCaption)/sizeof(wchar_t));
				    MessageBoxW(hwndDlg, filename.c_str(), szCaption, MB_OK | MB_ICONEXCLAMATION);
				}
			    }
			    break;
                    }
            }
            // pass messages to parent
            return CWizard::PageDispatch(hwndDlg, uMsg, wParam, lParam, psp);
        }
        
        /// @brief Espera a que Xming escuche en su puerto (hasta 12 s).
        /// Termina antes si el proceso de Xming muere, por ejemplo porque el
        /// display ya estaba en uso.
        bool WaitForServer(HANDLE hServer, unsigned long display)
        {
            DWORD start = GetTickCount();
            while (GetTickCount() - start < 12000)
            {
                if (DisplayListening(display))
                    return true;
                if (WaitForSingleObject(hServer, 100) != WAIT_TIMEOUT)
                    return false;
            }
            return false;
        }

        /// @brief Do the actual start of Xming and clients
	void StartUp()
	{
	    std::wstring buffer;
	    std::wstring client;
	    bool msdos = false;

	    // Display vacío: el primero libre. Un .xlaunch puede traer cualquier
	    // texto, y va a la línea de comandos de Xming: solo se aceptan dígitos.
	    if (config.display.empty())
		config.display = FreeDisplay();
	    if (!ValidDisplay(config.display))
	    {
		MessageFromResources(NULL, IDS_BAD_DISPLAY_MESS, IDS_BAD_DISPLAY_CAP,
				     MB_OK | MB_ICONEXCLAMATION, config.display.c_str());
		return;
	    }
	    unsigned long display_number = wcstoul(config.display.c_str(), NULL, 10);
	    // Display ocupado: Xming no podría arrancar y el programa se conectaría
	    // al otro servidor que ya escucha en ese puerto.
	    if (DisplayListening(display_number))
	    {
		MessageFromResources(NULL, IDS_DISPLAY_IN_USE_MESS, IDS_DISPLAY_IN_USE_CAP,
				     MB_OK | MB_ICONEXCLAMATION, (L":" + config.display).c_str());
		return;
	    }

            // Construct display strings
	    std::wstring display_id = L":" + config.display;
	    std::wstring display = L"127.0.0.1" + display_id + L".0";

#ifdef _DEBUG
            // Debug only: Switch to Xming installation directory
	    SetCurrentDirectory(L"C:\\Programme\\Xming");
#endif	    

            // Build Xming commandline
	    {
		std::wstring xming = ModuleDir() + L"Xming.exe";
		buffer = (FileExists(xming) ? QuotePath(xming) : std::wstring(L"Xming")) + L" " + display_id + L" ";
	    }
	    switch (config.window)
	    {
		case CConfig::MultiWindow:
		    buffer += L"-multiwindow ";
		    break;
		case CConfig::Fullscreen:
		    buffer += L"-fullscreen ";
		    break;
		case CConfig::Nodecoration:
		    buffer += L"-nodecoration ";
		    break;
		default:
		    break;
	    }
            // Add XDMCP parameter
	    if (config.client == CConfig::XDMCP)
	    {
		if (config.broadcast)
		    buffer += L"-broadcast ";
		else 
		{
		    if (config.indirect)
			buffer += L"-indirect ";
		    else
			buffer += L"-query ";
		    buffer += config.xdmcp_host;
            buffer += L" ";
		}
	    }
            // El clipboard está activo por defecto en el servidor: solo hay que
            // indicarlo cuando el usuario lo desmarca.
            if (!config.clipboard)
                buffer += L"-noclipboard ";
	    if (config.no_access_control)
		buffer += L"-ac ";
            if (!config.font_server.empty())
            {
                buffer += L"-fp tcp/";
                buffer += config.font_server;
                buffer += L":7100 ";
            }
            if (!config.extra_params.empty())
            {
                buffer += config.extra_params;
                buffer += L" ";
            }
            
            // Construct client commandline
	    if (config.client == CConfig::StartProgram)
	    {
		if (config.clientstart != CConfig::Local)
		{
                    std::wstring host = config.host;
                    if (!config.user.empty())
                        host = config.user + L"@" + config.host;
		    if (config.clientstart == CConfig::PuTTY)
		    {
			if (!config.protocol_path.empty())
			    client = QuotePath(config.protocol_path + L"plink.exe") + L" ";
			else
			    client = L"plink ";
			client += L"-ssh -X ";
			if (!config.password.empty())
				client += L"-pw " + QuoteArg(config.password) + L" ";
		    }
		    else
		    {
			std::wstring ssh = config.protocol_path.empty()
			    ? FindWindowsOpenSSH() : config.protocol_path + L"ssh.exe";
			if (!GetEnvironmentVariable(L"SSH_AGENT_PID",0,0)) msdos = true;
			client = (ssh.empty() ? std::wstring(L"ssh") : QuotePath(ssh)) + L" -Y ";
			// Conexiones lentas (casilla de compresión): mantener viva la sesión
			if (config.compress)
			    client += L"-o ServerAliveInterval=30 ";
		    }
		    if (config.compress)
			client += L"-C ";
		    if (!config.extra_ssh.empty())
		    {
			client += config.extra_ssh;
			client += L" ";
		    }
		    client += host.c_str();
		    client += L" ";
		}
		client += config.program.c_str();
		if (!wcscmp(config.program.c_str(), L"testplink") && config.clientstart == CConfig::PuTTY)
		    MessageBoxW(NULL, client.c_str(), L"XLaunch Test 'plink command line'", MB_OK | MB_ICONINFORMATION);
	    }

            // Prepare program startup
     	    STARTUPINFOW si, sic;
	    PROCESS_INFORMATION pi, pic;

	    ZeroMemory( &si, sizeof(si) );
	    si.cb = sizeof(si);
	    ZeroMemory( &pi, sizeof(pi) );
	    ZeroMemory( &sic, sizeof(sic) );
	    sic.cb = sizeof(sic);
	    ZeroMemory( &pic, sizeof(pic) );

	    // Start Xming process. CreateProcessW puede escribir en la línea de
	    // comandos: se le pasa una copia modificable.
	    std::vector<wchar_t> cmdline(buffer.begin(), buffer.end());
	    cmdline.push_back(L'\0');
	    if( !CreateProcessW( NULL, &cmdline[0], NULL, NULL,
                        FALSE, 0, NULL, NULL, &si, &pi ))
		throw win32_error("CreateProcess failed");

	    if (!client.empty())
	    {
                // Set DISPLAY variable
		SetEnvironmentVariableW(L"DISPLAY",display.c_str());

                // Esperar al servidor; si no arranca, no lanzar el programa
                if (!WaitForServer(pi.hProcess, display_number))
                {
		    MessageFromResources(NULL, 0, IDS_OPEN_FAIL, MB_OK | MB_ICONEXCLAMATION,
					 display.c_str());
		    TerminateProcess(pi.hProcess, (DWORD)-1);
		    CloseHandle(pi.hProcess);
		    CloseHandle(pi.hThread);
		    return;
                }

                // Hide a console window, unless msdos is true
		sic.dwFlags = STARTF_USESHOWWINDOW;
		sic.wShowWindow = SW_HIDE;
		if (msdos) sic.wShowWindow = SW_NORMAL;

		// Start the child process.
		std::vector<wchar_t> clientline(client.begin(), client.end());
		clientline.push_back(L'\0');
		if( !CreateProcessW( NULL, &clientline[0], NULL, NULL,
                            FALSE, 0, NULL, NULL, &sic, &pic ))
		{
		    MessageFromResources(NULL, 0, IDS_PROGRAM_START_FAIL,
					 MB_OK | MB_ICONEXCLAMATION, client.c_str());
		    TerminateProcess(pi.hProcess, (DWORD)-1);
		    CloseHandle(pi.hProcess);
		    CloseHandle(pi.hThread);
		    return;
		}
	    }

	    // Xming sigue abierto cuando termina el programa (se cierra desde su
	    // icono de la bandeja). Antes XLaunch lo cerraba en cuanto salía el
	    // primer programa, por ejemplo al cerrar la sesión ssh que lo lanzó.
	    WaitForSingleObject(pi.hProcess, INFINITE);

	    // Sin servidor, el programa ya no tiene dónde dibujar: cerrarlo
	    if (pic.hProcess)
	    {
		if (WaitForSingleObject(pic.hProcess, 0) == WAIT_TIMEOUT)
		    TerminateProcess(pic.hProcess, (DWORD)-1);
		CloseHandle( pic.hProcess );
		CloseHandle( pic.hThread );
	    }
	    CloseHandle( pi.hProcess );
	    CloseHandle( pi.hThread );
	}
};

int main(int, char **)
{
    try {
        InitCommonControls();
        CMyWizard dialog;
	wchar_t szMessage[MAX_MESSAGE];
	wchar_t szCaption[MAX_CAPTION];
	WSADATA wsa;

	// Sondeo TCP del servidor (WaitForServer, FreeDisplay)
	WSAStartup(MAKEWORD(2, 2), &wsa);

	bool skip_wizard = false;

	// Argumentos en UTF-16: las rutas con caracteres fuera de la página de
	// códigos ANSI ya no se pierden.
	int argc = 0;
	LPWSTR *argv = CommandLineToArgvW(GetCommandLineW(), &argc);
	if (!argv)
	    return -1;

	if (argc != 1 && argc != 3)
	{
		LoadStringW(GetModuleHandle(NULL), IDS_USAGE, szMessage, sizeof(szMessage)/sizeof(wchar_t));
		LoadStringW(GetModuleHandle(NULL), IDS_WRONG_OPTIONS, szCaption, sizeof(szCaption)/sizeof(wchar_t));
		MessageBoxW(NULL, szMessage, szCaption, MB_OK | MB_ICONEXCLAMATION);
		return -1;
	}

	for (int i = 1; i < argc; i++)
	{
	    std::wstring arg(argv[i]);
	    bool load = arg == L"-load", validate = arg == L"-validate", run = arg == L"-run";
	    if (!(load || validate || run) || i + 1 >= argc)
	    {
		MessageFromResources(NULL, 0, IDS_UNKNOWN_OPTION, MB_OK | MB_ICONEXCLAMATION,
				     arg.c_str());
		return -1;
	    }
	    std::wstring file = FindConfigFile(argv[++i]);
	    if (!FileRead(file.c_str()))
	    {
		MessageFromResources(NULL, 0, load ? IDS_CANNOT_LOAD
				     : validate ? IDS_CANNOT_VALIDATE : IDS_CANNOT_RUN,
				     MB_OK | MB_ICONEXCLAMATION, file.c_str());
		return -1;
	    }
	    dialog.LoadConfig(file.c_str(), validate);
	    dialog.StripStart();
	    if (!run)
		continue;

	    if (dialog.PasswordStart())
	    {
		if (dialog.PasswordStartPopulated())
		    dialog.InitPasswordMode();
		else
		    MessageFromResources(NULL, IDS_PASS_ENTRY_MESS, IDS_PASS_ENTRY_CAP,
					 MB_OK | MB_ICONINFORMATION);
	    }
	    else if (!dialog.StartPopulated())
		MessageFromResources(NULL, IDS_START_POP_MESS, IDS_START_POP_CAP,
				     MB_OK | MB_ICONINFORMATION);
	    else
		skip_wizard = true;
	}
	LocalFree(argv);

	int ret = 0;
        if (skip_wizard || (ret =dialog.ShowModal()) != 0)
	    dialog.StartUp();
	WSACleanup();
	return 0;
    } catch (std::runtime_error &e)
    {
        printf("Error: %s\n", e.what());
        return -1;
    }
}
