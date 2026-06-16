const assert = require("node:assert/strict");
const test = require("node:test");

const { parseReviewContent, decideShouldBlock } = require("./deepseek-review");

test("does not block when model returns BLOCK YES without parseable issues", () => {
  const review = parseReviewContent(`
✅ [deepseek-review] 未发现明显问题

BLOCK: YES
`);

  const decision = decideShouldBlock(review, {
    blockOnSevere: true,
  });

  assert.equal(review.errors.length, 0);
  assert.equal(review.blockFlag, "YES");
  assert.equal(decision.shouldBlock, false);
  assert.equal(decision.reason, "block_yes_without_errors");
});

test("blocks when model returns an ERROR and BLOCK YES", () => {
  const review = parseReviewContent(`
ERROR: [src/index.js:12] 未处理空指针异常
BLOCK: YES
`);

  const decision = decideShouldBlock(review, {
    blockOnSevere: true,
  });

  assert.equal(review.errors.length, 1);
  assert.equal(decision.shouldBlock, true);
  assert.equal(decision.reason, "block_yes_with_errors");
});
