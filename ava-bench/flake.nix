{
  description = "AVA-Bench: Raspberry Pi ML Benchmarking Suite";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        
        commonPackages = with pkgs; [
          python312
          uv # just better then poetry
          git
          just
          btop
          tree
        ];

        darwinPackages = with pkgs; lib.optionals stdenv.isDarwin [
        ];
        linuxPackages = with pkgs; lib.optionals stdenv.isLinux [
          lshw
          usbutils
        ];

        mlDeps = with pkgs; [
          pkg-config
          cmake
          opencv4
          ffmpeg
          libjpeg
          libpng
          glib
          stdenv.cc
        ];

      in
      {
        devShells = 
        {
            # TODO: Adjust these values to what the pi can actually do! 
            cores = 18;
            max-job = 6;
            default = pkgs.mkShell {
                buildInputs = commonPackages ++ darwinPackages ++ linuxPackages ++ mlDeps;
                NIX_BUILD_HOOK_BUFFER_SIZE = "8192";
                NIX_CURL_BUFFER_SIZE = "65536";

                shellHook = ''
                    # Simple colors
                    BLUE='\033[0;34m'
                    GREEN='\033[0;32m'
                    YELLOW='\033[1;33m'
                    NC='\033[0m' # No Color

                    echo -e "\n''${BLUE}=================================''${NC}"
                    echo -e "''${BLUE}  AVA-Bench Development Environment''${NC}"
                    echo -e "''${BLUE}=================================''${NC}"
                    echo -e "Platform: ''${YELLOW}${system}''${NC}"
                    echo -e "Python: ''${YELLOW}$(python --version)''${NC}"
                    echo -e "uv: ''${YELLOW}$(uv --version)''${NC}"
                    echo ""

                    # Create .venv if it doesn't exist
                    if [ ! -d ".venv" ]; then
                        echo "Creating Python virtual environment..."
                        uv venv
                    fi
                    
                    # Activate virtual environment
                    source .venv/bin/activate
                    echo -e "''${GREEN}✓ Virtual environment activated''${NC}"
                '';
                PYTHONPATH = "./src:$PYTHONPATH";
                
                LD_LIBRARY_PATH = pkgs.lib.optionalString pkgs.stdenv.isLinux 
                    "${pkgs.lib.makeLibraryPath mlDeps}";
                DYLD_LIBRARY_PATH = pkgs.lib.optionalString pkgs.stdenv.isDarwin
                    "${pkgs.lib.makeLibraryPath mlDeps}";
            };
        };      
    });
}