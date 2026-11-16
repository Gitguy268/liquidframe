# Template for Gitguy268/homebrew-tap Formula/liquidframe.rb. Fill in SHA256_SOURCE from the
# tag tarball after tagging. scripts/setup.py builds the interface and the Python environment
# inside the keg; the photo library itself lives outside it.
class Liquidframe < Formula
  desc "Local photo and media library with a Photos-style interface"
  homepage "https://github.com/Gitguy268/liquidframe"
  url "https://github.com/Gitguy268/liquidframe/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "SHA256_SOURCE"
  license "MIT"
  head "https://github.com/Gitguy268/liquidframe.git", branch: "main"

  depends_on "node" => :build
  depends_on "python@3.13"

  def install
    libexec.install Dir["*"]
    cd libexec do
      # Downloads the Python packages (PyTorch included) and npm packages, about 1 GB.
      system Formula["python@3.13"].opt_bin/"python3.13", "scripts/setup.py"
      rm_r Dir["frontend/node_modules", "companions/photobook/node_modules"]
    end

    home = OS.mac? ? "$HOME/Library/Application Support/LiquidFrame" : "${XDG_DATA_HOME:-$HOME/.local/share}/liquidframe"
    (bin/"liquidframe").write <<~SH
      #!/bin/sh
      # The library and its list of libraries stay outside the Homebrew keg, so upgrades keep them.
      : "${LIQUIDFRAME_STATE:=#{home}}"
      : "${LIQUIDFRAME_DATA:=$LIQUIDFRAME_STATE/library}"
      export LIQUIDFRAME_STATE LIQUIDFRAME_DATA
      mkdir -p "$LIQUIDFRAME_DATA"
      exec "#{libexec}/.venv/bin/python" -m liquidframe "$@"
    SH
  end

  def caveats
    <<~EOS
      Run `liquidframe` and open http://127.0.0.1:4320/ if it doesn't open by itself.
      The library is kept in #{OS.mac? ? "~/Library/Application Support/LiquidFrame" : "~/.local/share/liquidframe"}.
      Optional tools for more formats, video, OCR and metadata:
        brew install imagemagick jpeg-xl ffmpeg tesseract exiftool
    EOS
  end

  test do
    port = free_port
    pid = spawn({ "LIQUIDFRAME_STATE" => testpath.to_s }, bin/"liquidframe", "--port", port.to_s, "--no-browser")
    sleep 10
    assert_match "<html", shell_output("curl -s http://127.0.0.1:#{port}/")
  ensure
    Process.kill("TERM", pid) if pid
    Process.wait(pid) if pid
  end
end
