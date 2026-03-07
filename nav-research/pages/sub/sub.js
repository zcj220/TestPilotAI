Page({
  data: {
    log: '',
    pageStack: ''
  },

  onShow() {
    const pages = getCurrentPages();
    const stack = pages.map(p => p.route).join(' → ');
    this.addLog('onShow, 页面栈: ' + stack);
    this.setData({ pageStack: stack });
  },

  addLog(msg) {
    const time = new Date().toLocaleTimeString();
    const current = this.data.log;
    this.setData({ log: `[${time}] ${msg}\n${current}` });
  },

  goBack() {
    this.addLog('navigateBack');
    wx.navigateBack();
  },

  goBackDelta10() {
    this.addLog('navigateBack delta=10');
    wx.navigateBack({ delta: 10 });
  },

  reLaunchHome() {
    this.addLog('reLaunch /home');
    wx.reLaunch({ url: '/pages/home/home' });
  },

  redirectHome() {
    this.addLog('redirectTo /home');
    wx.redirectTo({ url: '/pages/home/home' });
  },

  goSubAgain() {
    this.addLog('navigateTo /sub (再跳一层)');
    wx.navigateTo({ url: '/pages/sub/sub' });
  }
})
