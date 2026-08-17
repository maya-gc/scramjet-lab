import { join } from 'path'
import { app, BrowserWindow, shell } from 'electron'
import { BackendProcess } from './backend'
import { registerIpc } from './ipc'

const isDev = !app.isPackaged

let mainWindow: BrowserWindow | null = null
const backend = new BackendProcess()

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 1080,
    minHeight: 680,
    show: false,
    backgroundColor: '#0a0a0c',
    title: 'SCRAMJET LAB',
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false
    }
  })

  mainWindow.on('ready-to-show', () => mainWindow?.show())
  mainWindow.on('closed', () => {
    mainWindow = null
  })

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http')) void shell.openExternal(url)
    return { action: 'deny' }
  })

  if (isDev && process.env.ELECTRON_RENDERER_URL) {
    void mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    void mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

app.whenReady().then(() => {
  registerIpc(backend)
  backend.on('status', (info) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('scramjet:backend-status', info)
    }
  })
  backend.start()
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('will-quit', () => backend.stop())