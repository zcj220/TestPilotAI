# TestPilot AI — 部署到生产服务器
# 用法：在项目根目录运行  .\deploy-web.ps1

$KEY = "D:\Projects\TestPilotAI\key\TestPilotAi.pem"
$SERVER = "ubuntu@82.157.97.179"
$REMOTE_DIR = "/var/www/testpilot"
$LOCAL_DIST = "D:\Projects\TestPilotAI\web\dist"

Write-Host "==> 构建前端..." -ForegroundColor Cyan
Set-Location D:\Projects\TestPilotAI\web
npm run build
if ($LASTEXITCODE -ne 0) { Write-Host "构建失败，已中止。" -ForegroundColor Red; exit 1 }

Write-Host "==> 上传到服务器..." -ForegroundColor Cyan
# 先在服务器端清理旧文件并重置权限
ssh -i $KEY -o StrictHostKeyChecking=no $SERVER "sudo chown -R ubuntu:ubuntu $REMOTE_DIR ; sudo chmod -R 755 $REMOTE_DIR ; rm -rf $REMOTE_DIR/assets"

# 上传新文件
scp -r -i $KEY -o StrictHostKeyChecking=no "$LOCAL_DIST\*" "${SERVER}:${REMOTE_DIR}/"
if ($LASTEXITCODE -ne 0) { Write-Host "上传失败。" -ForegroundColor Red; exit 1 }

# 修复上传后的权限（解决 Windows scp 权限传错问题）
ssh -i $KEY -o StrictHostKeyChecking=no $SERVER "find $REMOTE_DIR -type d -exec chmod 755 {} \; ; find $REMOTE_DIR -type f -exec chmod 644 {} \;"

Write-Host "==> 部署完成！" -ForegroundColor Green
Write-Host "    https://testpilot.xinzaoai.com" -ForegroundColor Green
