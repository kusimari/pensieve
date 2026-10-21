{
  description = "A tiny MCP memory server, one instance per store directory";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = { self, nixpkgs }:
    let
      forAll = nixpkgs.lib.genAttrs [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
    in {
      packages = forAll (system: {
        default = nixpkgs.legacyPackages.${system}.python3Packages.buildPythonApplication {
          pname = "pensieve";
          version = "0.1.0";
          pyproject = true;
          src = self;
          build-system = [ nixpkgs.legacyPackages.${system}.python3Packages.setuptools ];
        };
      });
    };
}
