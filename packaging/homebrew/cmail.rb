# Homebrew formula for cmail. This file is the source of truth; the copy users
# install from lives in the tap repository luongnv89/homebrew-tap at
# Formula/cmail.rb, so `brew install luongnv89/tap/cmail` works on macOS and Linux.
#
# Publishing a release (keep `version` in Cargo.toml, VERSION and the tag in sync):
#   1. Tag and push the release: git tag vX.Y.Z && git push origin vX.Y.Z
#      (.github/workflows/release.yml then publishes the prebuilt binaries).
#   2. Point `url` and `sha256` at the tag: scripts/update-formula.sh vX.Y.Z
#   3. Copy this file to Formula/cmail.rb in luongnv89/homebrew-tap, add cmail to
#      the tap README's formula table, and push it.
#   4. Check it: brew audit --strict --online luongnv89/tap/cmail
#                brew install --build-from-source luongnv89/tap/cmail && brew test cmail
class Cmail < Formula
  desc "Free custom-domain email with Cloudflare Email Routing"
  homepage "https://github.com/luongnv89/cmail"
  url "https://github.com/luongnv89/cmail/archive/refs/tags/v0.4.0.tar.gz"
  sha256 "2fe75929f8a219aaacc8825fc2e56044e0598f259481ba4655c7813d123e84d4"
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
