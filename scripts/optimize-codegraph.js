// CodeGraph 数据库优化脚本 v2
// 用法: node optimize-codegraph.js <db-path>
// 功能: PRAGMA 优化 + WAL checkpoint + VACUUM（自动回收碎片）
const path = require("path");
const { DatabaseSync } = require("node:sqlite");
const fs = require("fs");

const dbPath = process.argv[2];
if (!dbPath) { console.error("Usage: node optimize-codegraph.js <db-path>"); process.exit(1); }

const walPath = dbPath + "-wal";
const shmPath = dbPath + "-shm";

function getFileInfo() {
  const dbSize = fs.existsSync(dbPath) ? fs.statSync(dbPath).size : 0;
  const walSize = fs.existsSync(walPath) ? fs.statSync(walPath).size : 0;
  return { dbMB: (dbSize / 1024 / 1024).toFixed(2), walMB: (walSize / 1024 / 1024).toFixed(2) };
}

// 1. 读取当前状态
const before = getFileInfo();
console.log("Before: DB=" + before.dbMB + " MB, WAL=" + before.walMB + " MB");

// 2. 切换到 DELETE 模式，强制 WAL 合并到主库
const db = new DatabaseSync(dbPath, { open: true });
db.exec("PRAGMA journal_mode=DELETE");
db.exec("PRAGMA wal_checkpoint(TRUNCATE)");

// 3. 设置持久化配置
db.exec("PRAGMA auto_vacuum = FULL");

// 4. 连接级优化
db.exec("PRAGMA synchronous = NORMAL");
db.exec("PRAGMA wal_autocheckpoint = 2000");

// 5. 检查碎片率
const pageCount = db.prepare("PRAGMA page_count").get()["page_count"];
const freeCount = db.prepare("PRAGMA freelist_count").get()["freelist_count"];
const pageSize = db.prepare("PRAGMA page_size").get()["page_size"];
const fragPct = (freeCount / pageCount * 100).toFixed(1);
console.log("Pages: " + pageCount + ", Free: " + freeCount + ", Frag: " + fragPct + "%");

// 6. VACUUM（如果碎片率 > 10%）
if (freeCount / pageCount > 0.1) {
  console.log("Running VACUUM...");
  db.exec("VACUUM");
  console.log("VACUUM done");
}

db.close();

// 7. 清理残留 WAL/SHM
if (fs.existsSync(walPath)) fs.unlinkSync(walPath);
if (fs.existsSync(shmPath)) fs.unlinkSync(shmPath);

// 8. 切回 WAL 模式
const db2 = new DatabaseSync(dbPath, { open: true });
db2.exec("PRAGMA journal_mode=WAL");
db2.close();

// 9. 验证结果
const after = getFileInfo();
console.log("After: DB=" + after.dbMB + " MB, WAL=" + after.walMB + " MB");
console.log("Saved: " + (parseFloat(before.dbMB) + parseFloat(before.walMB) - parseFloat(after.dbMB) - parseFloat(after.walMB)).toFixed(2) + " MB");
