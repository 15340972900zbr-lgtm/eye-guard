Unicode true
Name "护眼工具"
OutFile "dist/EyeGuard-Setup-Windows-x64.exe"
InstallDir "$LOCALAPPDATA\Programs\EyeGuard"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails hide
ShowUninstDetails hide
SetOverwrite on

!include "MUI2.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
!define MUI_ICON "work/payload/assets/eye.ico"
!define MUI_UNICON "work/payload/assets/eye.ico"
!define MUI_ABORTWARNING
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\EyeGuard"

VIProductVersion "0.1.0.0"
VIAddVersionKey /LANG=2052 "ProductName" "护眼工具"
VIAddVersionKey /LANG=2052 "FileDescription" "护眼工具 Windows x64 安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "0.1.0"
VIAddVersionKey /LANG=2052 "LegalCopyright" "EyeGuard"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchEyeGuard
!define MUI_FINISHPAGE_RUN_TEXT "启动护眼工具"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

!macro RefuseRunning
    System::Call 'kernel32::OpenMutexW(i 0x100000, i 0, w "Local\EyeGuardWindows") p.r0'
    StrCmp $0 0 +5
    System::Call 'kernel32::CloseHandle(p r0)'
    MessageBox MB_OK|MB_ICONEXCLAMATION "请先在任务栏右下角退出护眼工具，再运行安装程序。" /SD IDOK
    SetErrorLevel 1
    Abort
!macroend

Function .onInit
    ${IfNot} ${IsNativeAMD64}
    ${OrIfNot} ${AtLeastWin10}
        MessageBox MB_OK|MB_ICONSTOP "此安装包适用于 64 位 Intel / AMD 的 Windows 10 和 11。" /SD IDOK
        SetErrorLevel 1
        Abort
    ${EndIf}
    SetShellVarContext current
    SetRegView 64
    !insertmacro RefuseRunning
FunctionEnd

Function un.onInit
    SetShellVarContext current
    SetRegView 64
    !insertmacro RefuseRunning
FunctionEnd

Function LaunchEyeGuard
    SetOutPath "$INSTDIR"
    Exec '"$INSTDIR\runtime\pythonw.exe" "$INSTDIR\app\start.pyw"'
FunctionEnd

Section "安装护眼工具"
    SetOutPath "$INSTDIR"
    File /r "work/payload/*"
    WriteUninstaller "$INSTDIR\Uninstall.exe"
    CreateShortCut "$SMPROGRAMS\护眼工具.lnk" "$INSTDIR\runtime\pythonw.exe" '"$INSTDIR\app\start.pyw"' "$INSTDIR\assets\eye.ico"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "护眼工具"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "0.1.0"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" '"$INSTDIR\assets\eye.ico"'
    WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKCU "${UNINSTALL_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
    Delete "$SMPROGRAMS\护眼工具.lnk"
    DeleteRegKey HKCU "${UNINSTALL_KEY}"
    Delete "$INSTDIR\README.txt"
    Delete "$INSTDIR\THIRD-PARTY.txt"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir /r "$INSTDIR\app"
    RMDir /r "$INSTDIR\assets"
    RMDir /r "$INSTDIR\runtime"
    RMDir "$INSTDIR"
SectionEnd
