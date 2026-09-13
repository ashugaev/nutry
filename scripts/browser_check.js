// Run with playwright-cli run-code --filename=scripts/browser_check.js on the app.
// All diary data below is synthetic; production authentication is never bypassed.
async page => {
  await page.route('https://telegram.org/js/telegram-web-app.js', route => route.fulfill({
    contentType: 'application/javascript',
    body: 'window.Telegram={WebApp:{initData:"test-only",initDataUnsafe:{user:{language_code:"ru"}},ready(){},expand(){},onEvent(){}}}'
  }));
  let mode = 'ok';
  let language = 'en';
  await page.route('**/api/stats?*', route => {
    if (mode !== 'ok') return route.fulfill({status: mode === 'expired' ? 401 : 503});
    const count = Number(route.request().url().split('days=')[1]);
    const days = Array.from({length: count}, (_, i) => ({
      date: new Date(Date.UTC(2026, 8, 13 - count + i)).toISOString().slice(0, 10),
      count: i === count - 1 ? 1 : 0,
      calories_kcal: i === count - 1 ? 840 : 0,
      protein_g: 42, carbs_g: 78, fat_g: 25,
      fiber_g: i === count - 1 ? 6.4 : 0, fiber_missing: 0,
      meals: i === count - 1 ? [{dish: '<script>unsafe title</script>', time: '10:30',
        calories_kcal: 840, protein_g: 42, carbs_g: 78, fat_g: 25, fiber_g: 6.4}] : []
    }));
    return route.fulfill({json: {today:'2026-09-12', timezone:'Europe/Moscow', language, days}});
  });
  await page.reload();
  await page.locator('#dashboard').waitFor({state:'visible'});
  if (await page.locator('#heading').innerText() !== 'Your day in food') throw new Error('Unselected Russian Telegram locale overrode English default');
  language='ru';
  await page.locator('#range').selectOption('7');
  await page.waitForFunction(() => document.querySelector('#heading').textContent === 'Твой день в еде');
  if (await page.locator('#calories').innerText() !== '840') throw new Error('Today total failed');
  if (!(await page.locator('#fiber').innerText()).includes('6,4')) throw new Error('Fiber total missing');
  if (await page.locator('#meals script').count()) throw new Error('Unsafe title rendered as HTML');
  await page.locator('#previous').click();
  if (!(await page.locator('#count').innerText()).includes('нет записей')) throw new Error('Empty day failed');
  await page.locator('#next').click();
  for (const value of ['7','90','30']) {
    await page.locator('#range').selectOption(value);
    await page.waitForFunction(count => document.querySelectorAll('.bar').length === count, Number(value));
  }
  if (await page.locator('#refresh').count()) throw new Error('Refresh button must be absent');
  mode='error'; await page.locator('#range').selectOption('7');
  await page.waitForFunction(() => document.querySelector('#status').textContent.includes('Не удалось'));
  mode='ok'; await page.locator('#range').selectOption('30');
  await page.locator('#status').waitFor({state:'hidden'});
  mode='expired'; await page.locator('#range').selectOption('7');
  await page.locator('#dashboard').waitFor({state:'hidden'});
  if (!(await page.locator('#status').innerText()).includes('Открой')) throw new Error('Expired session failed');
  mode='ok'; await page.reload();
  await page.locator('#dashboard').waitFor({state:'visible'});
  const before = await page.evaluate(() => window.visualViewport.scale);
  const touchAction = await page.evaluate(() => getComputedStyle(document.documentElement).touchAction);
  if (touchAction !== 'pan-x pan-y') throw new Error('Pinch zoom policy missing');
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Input.synthesizePinchGesture', {x: 180, y: 300, scaleFactor: 2, gestureSourceType: 'touch'});
  const after = await page.evaluate(() => window.visualViewport.scale);
  await cdp.detach();
  if (Math.abs(after - before) > 0.01) throw new Error('Pinch changed viewport scale');
  await page.evaluate(() => window.scrollTo(0, 200));
  if (await page.evaluate(() => window.scrollY) === 0) throw new Error('Page scrolling blocked');
  language='en';
  await page.reload();
  await page.locator('#dashboard').waitFor({state:'visible'});
  if (await page.locator('#heading').innerText() !== 'Your day in food') throw new Error('English selection not restored on reload');
  return 'PASS: both languages, English default despite Russian Telegram locale, mobile history/ranges/empty/error/auth, pinch disabled, scrolling preserved';
}
