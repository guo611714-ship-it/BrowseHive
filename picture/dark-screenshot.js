const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.goto('http://localhost:3099/');
  await page.evaluate(() => localStorage.setItem('officemind-theme', 'dark'));
  await page.reload();
  await page.waitForTimeout(2000);
  await page.screenshot({ path: 'd:/Users/lenovo/Desktop/claude workspace/picture/excel-dark-v2.png' });
  await browser.close();
  console.log('Dark mode screenshot saved');
})();
