// === TASK:WP-602:START ===
import { expect, test } from '@playwright/test'

test('information assistance browser shell is available for both demo channels', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Trợ lý bệnh viện' })).toBeVisible()
})
// === TASK:WP-602:END ===
