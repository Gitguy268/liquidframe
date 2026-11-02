"""Build the optional, local-only PhotoKit/ImageIO/Core Image adapter."""
from pathlib import Path
import subprocess,sys,plistlib,shutil,os
root=Path(__file__).resolve().parents[1]
if sys.platform!='darwin':raise SystemExit('The optional Mac adapter requires macOS.')
if not shutil.which('swiftc'):raise SystemExit('Install Apple Command Line Tools, then run this script again.')
app=root/'native/macos/LiquidFrameBridge.app';binary=app/'Contents/MacOS/LiquidFrameBridge';binary.parent.mkdir(parents=True,exist_ok=True)
subprocess.run(['swiftc','-module-cache-path',str(root/'native/macos/.module-cache'),'-O',str(root/'native/macos/main.swift'),'-o',str(binary),'-framework','Photos','-framework','ImageIO','-framework','CoreImage','-framework','AVFoundation'],check=True)
(app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'local.liquidframe.bridge','CFBundleName':'LiquidFrame Mac Adapter','CFBundleExecutable':'LiquidFrameBridge','CFBundlePackageType':'APPL','NSPhotoLibraryUsageDescription':'Import selected local photos and videos into LiquidFrame. Cloud-only originals are never downloaded.','LSUIElement':True}))
for attribute in ['com.apple.FinderInfo','com.apple.ResourceFork']:
 subprocess.run(['xattr','-dr',attribute,str(app)],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
subprocess.run(['codesign','--force','--sign','-',str(app)],check=True)
print('Built optional Mac adapter. Photos access is requested only when you choose Allow Photos access in Settings.')
