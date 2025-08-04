conda activate video
sudo rm -rf ~/.qt_material/
pip install -r requirements.txt
sudo rm -rf dist build
sudo bash icon_maker.sh translate.svg
sudo pyinstaller main.spec --clean
