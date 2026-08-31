import sys
import time
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings
from PyQt5.QtWebEngineCore import QWebEngineHttpRequest
import os

class OverlayBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        
    def initUI(self):
        # Configurar la ventana principal
        self.setWindowTitle('Overlay para Juego')
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |  # Mantener encima de otras ventanas
            Qt.FramelessWindowHint |   # Sin marco de ventana
            Qt.Tool                    # No mostrar en barra de tareas
        )
        
        # Hacer el fondo transparente
        self.setAttribute(Qt.WA_TranslucentBackground)
        # Hacer la ventana completamente pasiva
        self.setWindowFlags(self.windowFlags() | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        # Crear y configurar el navegador web
        self.browser = QWebEngineView()
        
        # Configurar el navegador para permitir transparencia
        self.browser.page().setBackgroundColor(Qt.transparent)
        self.browser.setStyleSheet("background:transparent;")
        self.browser.setAttribute(Qt.WA_TranslucentBackground, True)
        self.browser.setZoomFactor(0.9)
        # Deshabilitar barras de desplazamiento
        self.browser.page().settings().setAttribute(
            QWebEngineSettings.ShowScrollBars, False)
        
        # Configurar el tamaño y posición
        screen_geometry = QApplication.desktop().screenGeometry()
        self.setGeometry(0, 0, screen_geometry.width(), screen_geometry.height())
        
        # Establecer el navegador como widget central
        self.setCentralWidget(self.browser)
        self.setEnabled(False)
        # Cargar la URL con una página intermedia que aplique transparencia
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                html, body {
                    background-color: rgba(0, 0, 0, 0) !important;
                    margin: 0 !important;
                    padding: 0 !important;
                    overflow: hidden !important;
                    width: 100%;
                    height: 100%;
                }
                iframe {
                    width: 100%;
                    height: 100%;
                    border: none;
                    background-color: rgba(0, 0, 0, 0) !important;
                }
            </style>
        </head>
        <body>
            <iframe id="content" src="http://localhost:5000" sandbox="allow-same-origin allow-scripts"></iframe>
            <script>
                // Script para inyectar CSS en el iframe para asegurar transparencia
                window.onload = function() {
                    const iframe = document.getElementById('content');
                    iframe.onload = function() {
                        try {
                            const style = document.createElement('style');
                            style.textContent = `
                                html, body {
                                    background-color: rgba(0, 0, 0, 0) !important;
                                    margin: 0px auto !important;
                                    overflow: hidden !important;
                                }
                            `;
                            iframe.contentDocument.head.appendChild(style);
                        } catch(e) {
                            console.error("Error al inyectar estilos:", e);
                        }
                    };
                };
            </script>
        </body>
        </html>
        """
        
        # Cargar el HTML directamente
        self.browser.setHtml(html_content, QUrl("about:blank"))
        
        # Ajustar la transparencia general (0.0 completamente transparente, 1.0 opaco)
        self.setWindowOpacity(1.0)
        
    def keyPressEvent(self, event):
        # Tecla Escape para cerrar la aplicación
        if event.key() == Qt.Key_Escape:
            self.close()
        # F11 para alternar pantalla completa
        elif event.key() == Qt.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        # Ctrl+R para recargar
        elif event.key() == Qt.Key_R and event.modifiers() & Qt.ControlModifier:
            self.browser.reload()
        # Tecla F para pasar al primer plano
        elif event.key() == Qt.Key_F:
            self.activateWindow()
            
    def mousePressEvent(self, event):
        # Permitir arrastrar la ventana con el botón izquierdo
        if event.button() == Qt.LeftButton:
            self.dragPosition = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
            
    def mouseMoveEvent(self, event):
        # Mover la ventana al arrastrar
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.dragPosition)
            event.accept()

def main():
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--enable-gpu-rasterization --enable-oop-rasterization --ignore-gpu-blocklist --enable-accelerated-video-decode --enable-accelerated-mjpeg-decode --use-gl=desktop"
    
    app = QApplication(sys.argv)
    
    # Habilitar la transparencia en toda la aplicación
    app.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app.setAttribute(Qt.AA_EnableHighDpiScaling)
    
    browser = OverlayBrowser()
    browser.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()