#!/usr/bin/env node

/**
 * 在 git 提交时调用 DeepSeek 模型做代码审查的简单 CLI。
 *
 * 特性：
 *   - 读取当前已暂存的 diff
 *   - 要求 DeepSeek 按“严重 / 一般 / 建议”分级输出问题
 *   - 通过统一的 BLOCK 标记（BLOCK: YES/NO）决定是否阻止提交
 *
 * 行业通用的分级规则（可在 prompt 中自定义）：
 *   - 严重问题（会阻断提交）示例：
 *       * 明显的逻辑错误，可能导致线上功能不可用、数据损坏或严重体验问题
 *       * 潜在安全漏洞（SQL 注入、XSS、命令注入、敏感信息泄露等）
 *       * 明显违反项目基础规范，导致构建失败、测试无法通过等
 *   - 一般问题：
 *       * 可读性差、命名不清、缺少必要注释
 *       * 能运行但有潜在性能隐患
 *   - 建议/优化：
 *       * 代码风格、小重构建议、更优写法等
 *
 * 使用方式（建议）：
 *   1. 在项目根目录配置环境变量：
 *        export DEEPSEEK_API_KEY="你的_API_Key"
 *        export DEEPSEEK_API_BASE="https://api.deepseek.com"
 *        export DEEPSEEK_MODEL="deepseek-chat"
 *        # 可选：设置为 "0" 则不因为严重问题阻断提交，仅输出报告
 *        export DEEPSEEK_BLOCK_ON_SEVERE="1"
 *   2. 在 git hook（如 .git/hooks/pre-commit）中调用：
 *        node scripts/deepseek-review.js
 *
 * 注意：本脚本在当前沙箱里无法真正访问 DeepSeek，只是提供可在你本机直接运行的实现。
 */

const { execSync } = require("node:child_process");
const https = require("node:https");
const fs = require("node:fs");
const path = require("node:path");

// ANSI 颜色码
const colors = {
  reset: "\x1b[0m",
  red: "\x1b[31m",
  yellow: "\x1b[33m",
  blue: "\x1b[34m",
  green: "\x1b[32m",
  cyan: "\x1b[36m",
  gray: "\x1b[90m",
  bold: "\x1b[1m",
};

// 表情符号
const emojis = {
  error: "❌",
  warn: "⚠️",
  info: "💡",
  success: "✅",
  reviewing: "🔍",
  file: "📄",
};

const DEFAULT_RULES = {
  language: "zh-CN",
  name: "默认代码审查规则（通用行业规范）",
  description:
    "按照严重/一般/建议三个级别进行代码审查，并在存在严重问题时阻止提交。",
  severityLevels: {
    severe: {
      label: "严重问题",
      blockCommit: true,
      description:
        "可能导致功能不可用、数据损坏、安全漏洞（SQL 注入/XSS/命令注入/敏感信息泄露等）、或明显导致构建失败、测试无法通过的问题。"
    },
    major: {
      label: "一般问题",
      blockCommit: false,
      description:
        "可以运行，但存在潜在 Bug、性能隐患或较大维护成本的问题。"
    },
    suggestion: {
      label: "建议与优化",
      blockCommit: false,
      description:
        "风格、命名、结构优化、更优写法等，不影响功能正确性的改进建议。"
    }
  },
  focus: [
    "逻辑正确性与潜在 Bug",
    "边界条件与异常处理",
    "性能问题（明显低效的算法、N+1、重复 IO 等）",
    "安全问题（SQL 注入、XSS、命令注入、敏感信息泄露等）",
    "可维护性与可读性"
  ],
  outputFormat: {
    overview: "1. 总体评价（1-2 句）",
    severe:
      "2. 严重问题（如果没有，请写“无严重问题”）\n   - 【严重】描述问题 + 涉及的文件/大致位置 + 原因",
    major:
      "3. 一般问题（如果没有，请写“无一般问题”）\n   - 【一般】描述问题 + 涉及的文件/大致位置 + 原因",
    suggestion:
      "4. 建议与优化（如果没有，可以写“暂无明显优化建议”）",
    blockRule:
      "5. 最终结论（只保留一行，且用英文 BLOCK 标记，必须大写，方便脚本解析）：\n   - 如果存在必须在提交前修复的问题，请输出：\n     BLOCK: YES\n   - 如果可以允许提交，仅给出建议，请输出：\n     BLOCK: NO"
  },
  blockOnSevereDefault: true
};

function loadEnvLocal() {
  const envPath = path.join(process.cwd(), ".env.local");
  try {
    if (!fs.existsSync(envPath)) return;
    const content = fs.readFileSync(envPath, "utf8");
    const lines = content.split(/\r?\n/);
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const eqIndex = trimmed.indexOf("=");
      if (eqIndex === -1) continue;
      const key = trimmed.slice(0, eqIndex).trim();
      let value = trimmed.slice(eqIndex + 1).trim();
      // 去掉两边成对的引号（支持单引号和双引号）
      if (
        (value.startsWith("\"") && value.endsWith("\"")) ||
        (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1);
      }
      // 如果进程环境变量中还没有该值，则从 .env.local 写入
      if (key && process.env[key] == null) {
        process.env[key] = value;
      }
    }
  } catch (e) {
    console.warn(
      `[deepseek-review] 读取 .env.local 失败，将继续使用进程环境变量。原因：${e.message}`
    );
  }
}

function loadRules() {
  const rulesPath =
    process.env.DEEPSEEK_RULES_PATH ||
    path.join(process.cwd(), "rules.json");

  try {
    if (fs.existsSync(rulesPath)) {
      const raw = fs.readFileSync(rulesPath, "utf8");
      const json = JSON.parse(raw);
      return { ...DEFAULT_RULES, ...json };
    }
  } catch (e) {
    console.warn(
      `[deepseek-review] 读取规则文件失败，将使用内置默认规则。原因：${e.message}`
    );
  }

  return DEFAULT_RULES;
}

function run(cmd) {
  return execSync(cmd, { encoding: "utf8" }).trim();
}

function getStagedDiff() {
  try {
    // 只读取已暂存的变更，限制上下文行数，便于模型处理
    const diff = run("git diff --cached --unified=0");
    
    // 从 diff 中提取文件列表
    const files = [];
    const filePattern = /^diff --git a\/(.+?) b\/(.+?)$/gm;
    let match;
    while ((match = filePattern.exec(diff)) !== null) {
      const filePath = match[2];
      if (filePath && !files.includes(filePath)) {
        files.push(filePath);
      }
    }
    
    return { diff, files };
  } catch (e) {
    console.error("[deepseek-review] 读取 git diff 失败：", e.message);
    process.exit(1);
  }
}

function buildPrompt(diff, rules) {
  const focusList =
    Array.isArray(rules.focus) && rules.focus.length > 0
      ? rules.focus.map((item) => `- ${item}`).join("\n")
      : "- 逻辑正确性与潜在 Bug\n- 边界条件与异常处理\n- 性能问题\n- 安全问题\n- 可维护性与可读性";

  const severeDesc =
    rules.severityLevels?.severe?.description ||
    "可能导致功能不可用、数据损坏、安全漏洞或构建失败的问题。";
  const majorDesc =
    rules.severityLevels?.major?.description ||
    "可以运行，但存在潜在 Bug、性能隐患或较大维护成本的问题。";
  const suggestionDesc =
    rules.severityLevels?.suggestion?.description ||
    "风格、命名、结构优化、更优写法等，不影响功能正确性的建议。";

  const of = rules.outputFormat || {};

  return `
你是一个严格的资深代码审查专家，请审查下面这次 git 提交的变更 diff。

【审查重点】
${focusList}

【分级规则】
- 严重问题：${severeDesc}
- 一般问题：${majorDesc}
- 建议与优化：${suggestionDesc}

【重要提示 - 避免误报】
1. **Shebang 行识别**：
   - 如果脚本文件的第一行是 #!/usr/bin/env node 或类似的 shebang（以 #!/ 开头），说明已有正确的 shebang，不要报告"缺少 shebang"
   - 只有当脚本文件（.sh, .js, .py 等可执行脚本）的第一行完全没有 shebang 时，才报告此问题
   - 查看 diff 时，注意 + 开头的行表示新增，如果新增的第一行就是 shebang，说明已经正确添加

2. **格式问题判断**：
   - 如果代码格式已经符合规范（如已有正确的缩进、换行、shebang 等），不要报告格式问题
   - 只关注实际的功能缺陷、逻辑错误、安全问题等

3. **重复问题**：
   - 同一个问题只报告一次，不要重复输出
   - 如果多个文件有相同类型的问题，可以合并为一条，或分别列出但不要重复

【输出格式（必须严格遵守，类似程序报错样式，简洁明了）】
请按以下格式输出，每行一个问题，不要有多余的描述：

1. 严重问题（ERROR 级别，如果没有则跳过）：
   ERROR: [文件路径:行号] 问题描述
   例如：ERROR: [src/utils/api.js:42] 未处理空指针异常，可能导致程序崩溃

2. 一般问题（WARN 级别，如果没有则跳过）：
   WARN: [文件路径:行号] 问题描述
   例如：WARN: [src/components/Button.tsx:15] 缺少 PropTypes 类型检查

3. 建议与优化（INFO 级别，如果没有则跳过）：
   INFO: [文件路径:行号] 建议描述
   例如：INFO: [src/hooks/useAuth.js:8] 建议使用 useMemo 优化性能

4. 最终结论（必须独立一行，大写）：
   BLOCK: YES 或 BLOCK: NO

注意：
- 每行只输出一个问题，格式严格为：级别: [文件:行号] 描述
- 如果没有对应级别的问题，直接跳过该部分
- "BLOCK: YES/NO" 必须是独立一行，前后不要加其他字符
- 不要输出总体评价、总结等额外文字
- 仔细检查 diff，避免误报已正确实现的格式要求（如 shebang、缩进等）

下面是本次提交的 diff（统一 diff 格式）：

${diff}
`;
}

function callDeepseek({ apiKey, baseUrl, model, prompt }) {
  return new Promise((resolve, reject) => {
    const postData = JSON.stringify({
      model,
      messages: [
        { role: "system", content: "你是一个资深代码审查工程师，擅长发现问题并提出可行建议。" },
        { role: "user", content: prompt }
      ],
      temperature: 0.2
    });

    const url = new URL("/v1/chat/completions", baseUrl);

    const options = {
      method: "POST",
      hostname: url.hostname,
      path: url.pathname,
      port: url.port || 443,
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${apiKey}`,
        "Content-Length": Buffer.byteLength(postData)
      }
    };

    const req = https.request(options, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
          try {
            const json = JSON.parse(data);
            const content =
              json.choices?.[0]?.message?.content ||
              json.choices?.[0]?.text ||
              "";
            resolve(content.trim());
          } catch (e) {
            reject(new Error("解析 DeepSeek 响应失败：" + e.message));
          }
        } else {
          reject(
            new Error(
              `DeepSeek API 响应错误：${res.statusCode} ${res.statusMessage} ${data}`
            )
          );
        }
      });
    });

    req.on("error", (err) => reject(err));
    req.write(postData);
    req.end();
  });
}

async function main() {
  // 优先从 .env.local 加载配置（例如 DEEPSEEK_API_KEY）
  loadEnvLocal();

  const rules = loadRules();
  const { diff, files } = getStagedDiff();
  if (!diff) {
    console.log("[deepseek-review] 当前没有已暂存的变更，跳过代码审查。");
    process.exit(0);
  }

  const apiKey = process.env.DEEPSEEK_API_KEY;
  const baseUrl = process.env.DEEPSEEK_API_BASE || "https://api.deepseek.com";
  const model = process.env.DEEPSEEK_MODEL || "deepseek-chat";

  if (!apiKey) {
    console.error(
      "[deepseek-review] 未设置环境变量 DEEPSEEK_API_KEY，无法调用 DeepSeek。"
    );
    console.error(
      "请先在终端中设置，例如：export DEEPSEEK_API_KEY=\"你的_API_Key\""
    );
    process.exit(1);
  }

  // 显示审查信息
  console.log(`${colors.cyan}${colors.bold}[deepseek-review]${colors.reset} 开始代码审查...\n`);
  if (files.length > 0) {
    console.log(`${colors.gray}待审查文件 (${files.length} 个):${colors.reset}`);
    files.forEach((file, index) => {
      console.log(`  ${colors.gray}${index + 1}. ${emojis.file} ${file}${colors.reset}`);
    });
    console.log("");
  }

  const prompt = buildPrompt(diff, rules);

  // 显示审查进度
  if (files.length > 0) {
    const fileList = files.length <= 3 
      ? files.join(", ")
      : `${files.slice(0, 2).join(", ")} 等 ${files.length} 个文件`;
    process.stdout.write(`${colors.cyan}${emojis.reviewing} 正在审查: ${fileList}...${colors.reset}`);
  } else {
    process.stdout.write(`${colors.cyan}${emojis.reviewing} 正在审查代码...${colors.reset}`);
  }

  try {
    const content = await callDeepseek({ apiKey, baseUrl, model, prompt });
    
    // 清除进度提示（使用足够长的空格确保完全清除）
    const clearLine = "\r" + " ".repeat(100) + "\r";
    process.stdout.write(clearLine);
    
    // 解析 AI 返回的内容，按 ERROR/WARN/INFO 分类
    const lines = content.split(/\r?\n/);
    const errors = [];
    const warnings = [];
    const infos = [];
    let blockFlag = null;

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;

      // 提取 BLOCK 标记
      const blockMatch = trimmed.match(/^\s*BLOCK:\s*(YES|NO)\s*$/i);
      if (blockMatch) {
        blockFlag = blockMatch[1].toUpperCase();
        continue;
      }

      // 解析 ERROR/WARN/INFO 格式
      const errorMatch = trimmed.match(/^ERROR:\s*(.+)$/i);
      if (errorMatch) {
        errors.push(errorMatch[1]);
        continue;
      }

      const warnMatch = trimmed.match(/^WARN:\s*(.+)$/i);
      if (warnMatch) {
        warnings.push(warnMatch[1]);
        continue;
      }

      const infoMatch = trimmed.match(/^INFO:\s*(.+)$/i);
      if (infoMatch) {
        infos.push(infoMatch[1]);
        continue;
      }
    }

    // 按程序报错样式输出，带颜色和表情
    if (errors.length > 0 || warnings.length > 0 || infos.length > 0) {
      console.log(`\n${colors.bold}[deepseek-review] 代码审查发现问题：${colors.reset}\n`);
      
      if (errors.length > 0) {
        console.log(`${colors.red}${colors.bold}${emojis.error} 严重问题 (${errors.length}):${colors.reset}`);
        errors.forEach((msg) => {
          console.error(`  ${colors.red}ERROR:${colors.reset} ${msg}`);
        });
        console.log("");
      }

      if (warnings.length > 0) {
        console.log(`${colors.yellow}${colors.bold}${emojis.warn} 一般问题 (${warnings.length}):${colors.reset}`);
        warnings.forEach((msg) => {
          console.warn(`  ${colors.yellow}WARN:${colors.reset}  ${msg}`);
        });
        console.log("");
      }

      if (infos.length > 0) {
        console.log(`${colors.blue}${colors.bold}${emojis.info} 优化建议 (${infos.length}):${colors.reset}`);
        infos.forEach((msg) => {
          console.log(`  ${colors.blue}INFO:${colors.reset}  ${msg}`);
        });
        console.log("");
      }
    } else {
      console.log(`\n${colors.green}${emojis.success} [deepseek-review] 未发现明显问题${colors.reset}\n`);
    }

    // 根据模型返回的 BLOCK 标记决定是否阻止提交
    const envBlock = process.env.DEEPSEEK_BLOCK_ON_SEVERE;
    const blockOnSevere =
      envBlock === "0"
        ? false
        : envBlock === "1"
        ? true
        : !!rules.blockOnSevereDefault;
    let shouldBlock = false;

    if (blockFlag) {
      if (blockFlag === "YES") {
        shouldBlock = true;
      }
    } else {
      // 如果没有 BLOCK 标记，但有 ERROR 级别问题，也视为需要阻断
      if (errors.length > 0) {
        shouldBlock = true;
        console.warn(
          `${colors.yellow}[deepseek-review] 未找到 BLOCK 标记，但检测到 ERROR 级别问题，将阻止提交。${colors.reset}`
        );
      } else {
        console.warn(
          `${colors.yellow}[deepseek-review] 未在模型输出中找到 BLOCK: YES/NO 标记，将默认视为允许提交（BLOCK: NO）。${colors.reset}`
        );
      }
    }

    if (blockOnSevere && shouldBlock) {
      console.error(`\n${colors.red}${colors.bold}${emojis.error} [deepseek-review] 检测到严重问题，阻止本次提交。${colors.reset}\n`);
      process.exit(1);
    }

    process.exit(0);
  } catch (e) {
    // 清除进度提示
    const clearLine = "\r" + " ".repeat(100) + "\r";
    process.stdout.write(clearLine);
    console.error(`${colors.red}${emojis.error} [deepseek-review] 调用 DeepSeek 失败：${colors.reset} ${e.message}`);
    // 如果你希望"审查失败就阻止提交"，可以把下面改成 process.exit(1)
    process.exit(0);
  }
}

main();

