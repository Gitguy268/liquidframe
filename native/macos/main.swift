import Foundation
import Photos
import ImageIO
import CoreImage
import AVFoundation
#if canImport(Cinematic)
import Cinematic
#endif

// This bridge is an optional, separately launched app. PhotoKit never fetches from iCloud.
func emit(_ value: Any) { let data = try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]); FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data([10])) }
func fail(_ text: String) -> Never { FileHandle.standardError.write(Data(text.utf8)); exit(1) }
let command = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "capabilities"
let input = FileHandle.standardInput.readDataToEndOfFile()
let body = (try? JSONSerialization.jsonObject(with: input)) as? [String: Any] ?? [:]
func authorized() -> Bool { let status = PHPhotoLibrary.authorizationStatus(for: .readWrite); return status == .authorized || status == .limited }
func asset(_ id: String) -> PHAsset? { return PHAsset.fetchAssets(withLocalIdentifiers: [id], options: nil).firstObject }
func aux(_ path: String) -> (CGImageSource, [CFString: Any]?)? {
 guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil) else { return nil }
 let value = CGImageSourceCopyAuxiliaryDataInfoAtIndex(source, 0, kCGImageAuxiliaryDataTypeDisparity) ?? CGImageSourceCopyAuxiliaryDataInfoAtIndex(source, 0, kCGImageAuxiliaryDataTypeDepth)
 return (source, value as? [CFString: Any])
}
switch command {
case "capabilities":
 emit(["photo_library_import": true, "portrait_depth": CIFilter(name: "CIDepthBlurEffect") != nil, "cinematic_focus": false, "cinematic_inspection": true, "network_retrieval": false, "authorized": authorized(), "runtime": ProcessInfo.processInfo.operatingSystemVersionString])
case "authorize":
 let semaphore = DispatchSemaphore(value: 0); var status = PHAuthorizationStatus.notDetermined
 PHPhotoLibrary.requestAuthorization(for: .readWrite) { result in status = result; semaphore.signal() }; semaphore.wait()
 emit(["authorized": status == .authorized || status == .limited])
case "albums":
 guard authorized() else { fail("Allow Photos access in LiquidFrame Settings first.") }
 var rows: [[String: Any]] = []
 PHAssetCollection.fetchAssetCollections(with: .album, subtype: .any, options: nil).enumerateObjects { a, _, _ in rows.append(["id": a.localIdentifier, "name": a.localizedTitle ?? "Album", "count": PHAsset.fetchAssets(in: a, options: nil).count]) }
 emit(["albums": rows])
case "items":
 guard authorized() else { fail("Photos access is not authorized.") }
 let offset = max(0, body["offset"] as? Int ?? 0), limit = min(240, max(1, body["limit"] as? Int ?? 120)); var result: PHFetchResult<PHAsset>
 if let id = body["album"] as? String, let a = PHAssetCollection.fetchAssetCollections(withLocalIdentifiers: [id], options: nil).firstObject { result = PHAsset.fetchAssets(in: a, options: nil) } else { result = PHAsset.fetchAssets(with: nil) }
 var rows: [[String: Any]] = []
 if offset < result.count { for n in offset..<min(result.count, offset + limit) { let a = result.object(at: n); rows.append(["id": a.localIdentifier, "width": a.pixelWidth, "height": a.pixelHeight, "video": a.mediaType == .video, "date": a.creationDate.map { ISO8601DateFormatter().string(from: $0) } ?? "", "components": PHAssetResource.assetResources(for: a).map { ["name": $0.originalFilename, "type": $0.type.rawValue] }]) } }
 emit(["items": rows, "total": result.count])
case "import":
 guard authorized(), let ids = body["ids"] as? [String], ids.count <= 500, let destination = body["destination"] as? String else { fail("Choose up to 500 local Photos items.") }
 let folder = URL(fileURLWithPath: destination, isDirectory: true); try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true); var files: [String] = [], errors: [[String: String]] = []
 for id in ids { guard let a = asset(id) else { continue }; for resource in PHAssetResource.assetResources(for: a) {
  let name = URL(fileURLWithPath: resource.originalFilename).lastPathComponent; let url = folder.appendingPathComponent(UUID().uuidString + "-" + name)
  let options = PHAssetResourceRequestOptions(); options.isNetworkAccessAllowed = false
  let semaphore = DispatchSemaphore(value: 0); var errorText: String?
  PHAssetResourceManager.default().writeData(for: resource, toFile: url, options: options) { error in errorText = error?.localizedDescription; semaphore.signal() }; semaphore.wait()
  if let error = errorText { try? FileManager.default.removeItem(at: url); errors.append(["id": id, "error": error]) } else { files.append(url.path) }
 } }
 emit(["files": files, "errors": errors, "network_retrieval": false])
case "depth-info":
 guard let path = body["path"] as? String, let (_, data) = aux(path) else { fail("This image is unavailable.") }
 emit(["available": data != nil, "filter": CIFilter(name: "CIDepthBlurEffect") != nil])
case "depth":
 guard let path = body["path"] as? String, let output = body["output"] as? String, let (_, data) = aux(path), let data = data, let av = try? AVDepthData(fromDictionaryRepresentation: data), let source = CIImage(contentsOf: URL(fileURLWithPath: path)), let filter = CIFilter(name: "CIDepthBlurEffect") else { fail("This source does not contain a supported depth or disparity map.") }
 let depth = av.converting(toDepthDataType: kCVPixelFormatType_DisparityFloat32); let map = CIImage(cvPixelBuffer: depth.depthDataMap)
 filter.setValue(source, forKey: kCIInputImageKey); filter.setValue(map, forKey: "inputDisparityImage"); filter.setValue(min(22, max(1.4, body["aperture"] as? Double ?? 4)), forKey: "inputAperture")
 if let point = body["focus"] as? [Double], point.count == 2 { filter.setValue(CIVector(x: point[0], y: 1 - point[1], z: 0.03, w: 0.03), forKey: "inputFocusRect") }
 guard let image = filter.outputImage else { fail("The depth renderer could not render this image.") }
 let context = CIContext(options: [.cacheIntermediates: false]); try context.writeTIFFRepresentation(of: image.cropped(to: source.extent), to: URL(fileURLWithPath: output), format: .RGBA16, colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!, options: [:]); emit(["output": output, "engine": "Core Image CIDepthBlurEffect", "precision": "16-bit sRGB; source depth and renderer dependent"])
case "cinematic-info":
 guard let path = body["path"] as? String else { fail("Choose a video.") }
 let movie = AVURLAsset(url: URL(fileURLWithPath: path)); let semaphore = DispatchSemaphore(value: 0); var details: [String: Any] = [:]
 Task { do { let tracks = try await movie.load(.tracks); let metadata = try await movie.load(.metadata); details = ["tracks": tracks.count, "metadata_keys": metadata.compactMap { $0.identifier?.rawValue }, "focus_editing": false] } catch { details = ["error": error.localizedDescription] }; semaphore.signal() }; semaphore.wait(); emit(details)
case "devices": emit(["devices": []])
default: fail("Unknown local adapter operation.")
}
