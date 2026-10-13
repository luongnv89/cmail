# Homebrew formula for the luongnv89/tap tap (https://github.com/luongnv89/homebrew-tap).
# Refresh url and sha256 for a new tag with: scripts/update-formula.sh vX.Y.Z
class Cmail < Formula
  desc "Free custom-domain email with Cloudflare Email Routing"
  homepage "https://github.com/luongnv89/cmail"
  url "https://github.com/luongnv89/cmail/archive/refs/tags/v0.4.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "MIT"
  head "https://github.com/luongnv89/cmail.git", branch: "main"

  depends_on "rust" => :build

  def install
    system "cargo", "install", *std_cargo_args
    generate_completions_from_executable(bin/"cmail", "completion")
  end

  def caveats
    <<~EOS
      Configuration lives in ~/.config/cmail/.env (see `cmail config path`).
      Start with:
        cmail config init
        cmail setup
      GoDaddy automation (--registrar godaddy) additionally needs the gddy CLI.
    EOS
  end

  test do
    assert_match "cmail #{version}", shell_output("#{bin}/cmail --version")
    config = testpath/"cmail.env"
    assert_equal config.to_s, shell_output("#{bin}/cmail config path --config #{config}").strip
    refute_predicate config, :exist?
    output = shell_output("#{bin}/cmail doctor --offline --config #{config} 2>&1", 3)
    assert_match "configuration missing", output
    assert_match "cmail", shell_output("#{bin}/cmail completion bash")
  end
end
