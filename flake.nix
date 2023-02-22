{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" "x86_64-darwin" "aarch64-linux" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
      pkgs = forAllSystems (system: nixpkgs.legacyPackages.${system});

    in
    rec {
      packages = forAllSystems (system: {
        default =
          let
            spkgs = pkgs.${system};
            pypkgs = pkgs.${system}.python310Packages;
          in
          pypkgs.buildPythonPackage {
            pname = "testbench";
            version = "2.0";
            src = self;

            doCheck = false;
            buildInputs =  with pypkgs; [ setuptools ];
          };
      });



      devShells = forAllSystems (system: {
        default =
          let
            spkgs = pkgs.${system};
            pypkgs = pkgs.${system}.python310Packages;
          in
          pkgs.${system}.mkShellNoCC {
            packages = with spkgs; [

            ];
        };
      });
    };
}
