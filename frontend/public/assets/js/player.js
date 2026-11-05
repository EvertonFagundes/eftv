// player.js - Controller do player (adaptado do embed/player.html original)
import { utils } from './utils.js'

export const player = {
  video: null,
  currentSource: null,
  hls: null,
  dashPlayer: null,
  tsPlayer: null,
  _listeners: new Set(),

  subscribe(listener) {
    this._listeners.add(listener)
    return () => this._listeners.delete(listener)
  },

  _notify(event, data) {
    this._listeners.forEach(fn => fn(event, data))
  },

  init(videoElement) {
    this.video = videoElement
    this._setupEventListeners()
  },

  _setupEventListeners() {
    if (!this.video) return

    this.video.addEventListener('loadstart', () => this._notify('loadstart'))
    this.video.addEventListener('loadeddata', () => this._notify('loadeddata'))
    this.video.addEventListener('canplay', () => this._notify('canplay'))
    this.video.addEventListener('play', () => this._notify('play'))
    this.video.addEventListener('pause', () => this._notify('pause'))
    this.video.addEventListener('ended', () => this._notify('ended'))
    this.video.addEventListener('error', (e) => this._notify('error', e))
    this.video.addEventListener('waiting', () => this._notify('waiting'))
    this.video.addEventListener('playing', () => this._notify('playing'))
  },

  async load(sourceUrl, type = 'hls', token = null, drmLicenseUrl = null) {
    this.stop()
    this.currentSource = { url: sourceUrl, type, token, drmLicenseUrl }

    try {
      switch (type) {
        case 'hls':
          await this._loadHls(sourceUrl, token)
          break
        case 'dash':
          await this._loadDash(sourceUrl, token, drmLicenseUrl)
          break
        case 'ts':
          await this._loadTs(sourceUrl, token)
          break
        case 'mp4':
          this._loadMp4(sourceUrl)
          break
        default:
          throw new Error(`Tipo de stream não suportado: ${type}`)
      }
    } catch (error) {
      this._notify('error', error)
      throw error
    }
  },

  async _loadHls(url, token) {
    if (!window.Hls) {
      throw new Error('Hls.js não carregado')
    }

    if (this.hls) {
      this.hls.destroy()
    }

    this.hls = new window.Hls({
      enableWorker: true,
      lowLatencyMode: true,
      xhrSetup: (xhr, url) => {
        if (token) {
          xhr.setRequestHeader('Authorization', `Bearer ${token}`)
        }
      },
    })

    this.hls.loadSource(url)
    this.hls.attachMedia(this.video)

    return new Promise((resolve, reject) => {
      this.hls.on(window.Hls.Events.MANIFEST_PARSED, () => {
        this._notify('ready')
        resolve()
      })
      this.hls.on(window.Hls.Events.ERROR, (event, data) => {
        if (data.fatal) {
          reject(new Error(`Erro HLS: ${data.type} - ${data.details}`))
        }
      })
    })
  },

  async _loadDash(url, token, drmLicenseUrl) {
    if (!window.dashjs) {
      throw new Error('dash.js não carregado')
    }

    if (this.dashPlayer) {
      this.dashPlayer.destroy()
    }

    this.dashPlayer = window.dashjs.MediaPlayer().create()
    this.dashPlayer.initialize(this.video, url, false)

    if (token) {
      this.dashPlayer.setProtectionData({
        'com.widevine.alpha': {
          serverURL: drmLicenseUrl || '',
          httpRequestHeaders: {
            'Authorization': `Bearer ${token}`,
          },
        },
      })
    }

    return new Promise((resolve, reject) => {
      this.dashPlayer.on(window.dashjs.MediaPlayer.events.STREAM_INITIALIZED, () => {
        this._notify('ready')
        resolve()
      })
      this.dashPlayer.on(window.dashjs.MediaPlayer.events.ERROR, (e) => {
        reject(new Error(`Erro DASH: ${e.error?.message || e}`))
      })
    })
  },

  async _loadTs(url, token) {
    if (!window.mpegts) {
      throw new Error('mpegts.js não carregado')
    }

    if (this.tsPlayer) {
      this.tsPlayer.destroy()
    }

    this.tsPlayer = window.mpegts.createPlayer({
      type: 'mse',
      isLive: true,
      url,
      headers: token ? { 'Authorization': `Bearer ${token}` } : {},
    })

    this.tsPlayer.attachMediaElement(this.video)
    this.tsPlayer.load()
    this.tsPlayer.play()

    return new Promise((resolve, reject) => {
      this.tsPlayer.on(window.mpegts.Events.LOADED_METADATA, () => {
        this._notify('ready')
        resolve()
      })
      this.tsPlayer.on(window.mpegts.Events.ERROR, (type, details) => {
        reject(new Error(`Erro MPEG-TS: ${type} - ${details}`))
      })
    })
  },

  _loadMp4(url) {
    this.video.src = url
    this.video.load()
    return Promise.resolve()
  },

  play() {
    return this.video?.play()
  },

  pause() {
    this.video?.pause()
  },

  stop() {
    if (this.video) {
      this.video.pause()
      this.video.src = ''
      this.video.load()
    }
    if (this.hls) {
      this.hls.destroy()
      this.hls = null
    }
    if (this.dashPlayer) {
      this.dashPlayer.destroy()
      this.dashPlayer = null
    }
    if (this.tsPlayer) {
      this.tsPlayer.destroy()
      this.tsPlayer = null
    }
    this.currentSource = null
  },

  seek(time) {
    if (this.video) {
      this.video.currentTime = time
    }
  },

  setVolume(volume) {
    if (this.video) {
      this.video.volume = Math.max(0, Math.min(1, volume))
    }
  },

  setMuted(muted) {
    if (this.video) {
      this.video.muted = muted
    }
  },

  setPlaybackRate(rate) {
    if (this.video) {
      this.video.playbackRate = rate
    }
  },

  toggleFullscreen() {
    if (!this.video) return
    if (document.fullscreenElement) {
      document.exitFullscreen()
    } else {
      this.video.requestFullscreen().catch(() => {})
    }
  },

  isPlaying() {
    return this.video && !this.video.paused && !this.video.ended
  },

  getCurrentTime() {
    return this.video?.currentTime || 0
  },

  getDuration() {
    return this.video?.duration || 0
  },

  getBuffered() {
    return this.video?.buffered || { length: 0, start: () => 0, end: () => 0 }
  },
}

export default player