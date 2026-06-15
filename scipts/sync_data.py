import os
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 远程 clone 地址
REPO_URL = "https://github.com/Anduin2017/HowToCook.git"
# 本地克隆目录
TARGET_DIR = os.path.join("data", "HowToCook")

def check_git_installed():
    """检查 Git 是否已安装."""
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("Git is not installed or not in the system's PATH. Please install Git to continue.")
        return False

def sync_repo():
    """
    同步仓库数据
    Clone HowToCook 仓库, 如果仓库不存在就clone
    或仓库已存在时拉取最新变更.
    """
    if not check_git_installed():
        return

    if os.path.exists(TARGET_DIR):
        logger.info(f"Repository already exists at {TARGET_DIR}. Pulling latest changes...")
        try:
            # 检查是否为 Git 仓库目录
            if not os.path.isdir(os.path.join(TARGET_DIR, '.git')):
                logger.error(f"{TARGET_DIR} exists but is not a git repository. Please remove it and run the script again.")
                return

            subprocess.run(["git", "pull"], cwd=TARGET_DIR, check=True)
            logger.info("Successfully pulled latest changes.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error pulling latest changes: {e}")
    else:
        logger.info(f"Cloning repository from {REPO_URL} into {TARGET_DIR}...")
        try:
            subprocess.run(["git", "clone", REPO_URL, TARGET_DIR], check=True)
            logger.info("Repository cloned successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error cloning repository: {e}")

if __name__ == "__main__":
    sync_repo()
