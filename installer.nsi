!define APP_NAME "Git Dummy"
!define APP_EXE "GitDummy.exe"
!define INSTALL_DIR "$PROGRAMFILES\GitDummy"
!define UNINSTALLER "Uninstall.exe"

Name "${APP_NAME}"
OutFile "dist\GitDummy-windows.exe"
InstallDir "${INSTALL_DIR}"
InstallDirRegKey HKLM "Software\GitDummy" "Install_Dir"
RequestExecutionLevel admin
SetCompressor lzma

Page directory
Page instfiles

UninstPage uninstConfirm
UninstPage instfiles

Section "Install"
    SetOutPath "$INSTDIR"
    File /r "dist\GitDummy\*.*"

    ; Start Menu shortcut
    CreateDirectory "$SMPROGRAMS\Git Dummy"
    CreateShortcut "$SMPROGRAMS\Git Dummy\Git Dummy.lnk" "$INSTDIR\${APP_EXE}"
    CreateShortcut "$SMPROGRAMS\Git Dummy\Uninstall.lnk" "$INSTDIR\${UNINSTALLER}"

    ; Desktop shortcut
    CreateShortcut "$DESKTOP\Git Dummy.lnk" "$INSTDIR\${APP_EXE}"

    ; Registry entry for uninstaller
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GitDummy" "DisplayName" "${APP_NAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GitDummy" "UninstallString" "$INSTDIR\${UNINSTALLER}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GitDummy" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GitDummy" "DisplayIcon" "$INSTDIR\${APP_EXE}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GitDummy" "Publisher" "BruhClient"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GitDummy" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GitDummy" "NoRepair" 1

    WriteUninstaller "$INSTDIR\${UNINSTALLER}"

    ; Launch the app after install (manual or silent /S). Route through
    ; explorer.exe so the launched app inherits its un-elevated token instead
    ; of running with this (admin) installer's privileges.
    Exec '"$WINDIR\explorer.exe" "$INSTDIR\${APP_EXE}"'
SectionEnd

Section "Uninstall"
    Delete "$INSTDIR\${UNINSTALLER}"
    RMDir /r "$INSTDIR"
    Delete "$SMPROGRAMS\Git Dummy\Git Dummy.lnk"
    Delete "$SMPROGRAMS\Git Dummy\Uninstall.lnk"
    RMDir "$SMPROGRAMS\Git Dummy"
    Delete "$DESKTOP\Git Dummy.lnk"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GitDummy"
    DeleteRegKey HKLM "Software\GitDummy"
SectionEnd
