sudo rm -rf dist build
bash icon_maker.sh translate.svg
sudo pyinstaller main.spec src/main.py --clean
