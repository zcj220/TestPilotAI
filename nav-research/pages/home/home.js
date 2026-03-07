Page({
  data: {
    log: '',
    counter: 0
  },

  onShow() {
    const app = getApp();
    app.globalData.counter++;
    this.addLog('onShow触发, counter=' + app.globalData.counter);
  },

  addLog(msg) {
    const time = new Date().toLocaleTimeString();
    const current = this.data.log;
    this.setData({ log: `[${time}] ${msg}\n${current}` });
  },

  goSub() {
    this.addLog('navigateTo /sub');
    wx.navigateTo({ url: '/pages/sub/sub' });
  },

  testReLaunch() {
    this.addLog('reLaunch /home');
    wx.reLaunch({ url: '/pages/home/home' });
  },

  testRedirectTo() {
    this.addLog('redirectTo /home (自己跳自己)');
    wx.redirectTo({ url: '/pages/home/home' });
  },

  clearLog() {
    this.setData({ log: '' });
  }
})
