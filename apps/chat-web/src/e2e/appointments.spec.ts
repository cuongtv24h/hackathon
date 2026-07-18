// === TASK:WP-604:START ===
import { expect, test } from '@playwright/test'

test('appointments browser shell exposes chat web runtime for booking/status flows', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Trợ lý bệnh viện' })).toBeVisible()
  await expect(page).toHaveTitle('Chat Web')
})
// === TASK:WP-604:END ===
