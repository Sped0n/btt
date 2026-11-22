import CoreML
import Foundation
import Vision

struct TextLine: Encodable {
    let text: String
    let confidence: Float
    let x: Double
    let y: Double
}

let encoder = JSONEncoder()
let fast = CommandLine.arguments.contains("--fast")
while let input = readLine() {
    guard let image = Data(base64Encoded: input) else {
        throw CocoaError(.fileReadCorruptFile)
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = fast ? .fast : .accurate
    request.recognitionLanguages = ["en-GB"]
    request.usesLanguageCorrection = true
    // The default accelerator backend can hang partway through this recording.
    for (stage, devices) in try request.supportedComputeStageDevices {
        if let cpu = devices.first(where: { if case .cpu = $0 { true } else { false } }) {
            request.setComputeDevice(cpu, for: stage)
        }
    }
    try VNImageRequestHandler(data: image).perform([request])
    let lines = (request.results ?? []).compactMap { result -> TextLine? in
        guard let candidate = result.topCandidates(1).first else { return nil }
        return TextLine(text: candidate.string, confidence: candidate.confidence,
                        x: result.boundingBox.minX, y: 1 - result.boundingBox.midY)
    }
    FileHandle.standardOutput.write(try encoder.encode(lines) + Data([10]))
}
