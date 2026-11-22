import Cocoa
import FlutterMacOS

class MainFlutterWindow: NSWindow {
  override func awakeFromNib() {
    let flutterViewController = FlutterViewController()
    self.contentViewController = flutterViewController
    // Room for the session list beside a session; never so small the two panes squeeze
    self.title = "Loop Runner"
    self.minSize = NSSize(width: 900, height: 600)
    self.setContentSize(NSSize(width: 1280, height: 820))
    self.center()

    RegisterGeneratedPlugins(registry: flutterViewController)

    super.awakeFromNib()
  }
}
