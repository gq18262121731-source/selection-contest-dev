# 设备绑定错误修复指南

## 错误信息

```
Database "UNIQUE constraint failed: device_bindings.device_mac"
```

## 问题原因

这个错误表示：**尝试绑定一个已经被绑定过的手环**

可能的情况：
1. 手环已经绑定到当前用户
2. 手环已经绑定到其他用户
3. 移动端本地数据库中有旧的绑定记录

## 解决方案

### 方案1：先解绑再重新绑定（推荐）

#### 步骤1：在手机APP中解绑设备

1. 打开APP
2. 进入"设备管理"或"我的设备"
3. 找到要绑定的手环
4. 点击"解绑"或"删除设备"
5. 确认解绑

#### 步骤2：重新绑定

1. 返回设备列表
2. 点击"添加设备"或"绑定手环"
3. 扫描或输入手环MAC地址
4. 完成绑定

### 方案2：清除APP数据（如果方案1不行）

#### Android设备

1. 打开"设置" → "应用"
2. 找到健康监测APP
3. 点击"存储"
4. 点击"清除数据"（注意：会清除所有本地数据）
5. 重新打开APP并登录
6. 重新绑定手环

#### iOS设备

1. 卸载APP
2. 重新安装APP
3. 登录账号
4. 重新绑定手环

### 方案3：后端解绑设备

如果手环已经绑定到其他用户，需要管理员在后端解绑：

#### 使用API解绑

```bash
# 查看设备信息
curl http://localhost:8000/api/v1/devices/{MAC地址}

# 解绑设备（需要管理员权限）
curl -X POST http://localhost:8000/api/v1/devices/unbind \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {管理员token}" \
  -d '{
    "mac_address": "53:57:08:XX:XX:XX",
    "operator_id": "admin",
    "reason": "重新绑定"
  }'
```

#### 使用数据库直接操作

```bash
# 连接到数据库
sqlite3 data/app.db

# 查看设备绑定状态
SELECT mac_address, user_id, bind_status FROM devices;

# 解绑设备（将user_id设为NULL，bind_status设为unbound）
UPDATE devices 
SET user_id = NULL, bind_status = 'unbound' 
WHERE mac_address = '53:57:08:XX:XX:XX';

# 退出
.quit
```

### 方案4：检查是否重复绑定

有时候设备实际上已经绑定成功，只是APP显示错误。

#### 检查步骤

1. 刷新设备列表（下拉刷新）
2. 查看"我的设备"中是否已经有该手环
3. 如果已经存在，直接使用即可

## 预防措施

### 1. 绑定前检查

在绑定新设备前：
- 确认设备未被其他用户绑定
- 如果是更换用户，先解绑再绑定

### 2. 正确的绑定流程

```
1. 扫描/输入MAC地址
2. APP检查设备状态
3. 如果已绑定 → 提示用户先解绑
4. 如果未绑定 → 执行绑定
5. 绑定成功 → 更新本地数据库
```

### 3. 处理绑定冲突

如果出现绑定冲突：
- 不要重复点击绑定按钮
- 先检查设备当前状态
- 必要时先解绑再绑定

## 技术细节

### 数据库约束

移动端本地数据库中的约束：
```sql
CREATE TABLE device_bindings (
    device_mac TEXT PRIMARY KEY,  -- 唯一约束
    user_id TEXT NOT NULL,
    bound_at TIMESTAMP,
    ...
);
```

`device_mac`字段有`PRIMARY KEY`约束，意味着：
- 每个MAC地址只能有一条记录
- 重复插入会触发`UNIQUE constraint failed`错误

### 正确的处理方式

```dart
// 绑定前先检查
Future<void> bindDevice(String macAddress) async {
  // 1. 检查是否已存在
  final existing = await _db.query(
    'device_bindings',
    where: 'device_mac = ?',
    whereArgs: [macAddress],
  );
  
  // 2. 如果存在，先删除
  if (existing.isNotEmpty) {
    await _db.delete(
      'device_bindings',
      where: 'device_mac = ?',
      whereArgs: [macAddress],
    );
  }
  
  // 3. 插入新记录
  await _db.insert('device_bindings', {
    'device_mac': macAddress,
    'user_id': userId,
    'bound_at': DateTime.now().toIso8601String(),
  });
}
```

## 常见问题

### Q1: 为什么会出现这个错误？

**A**: 通常是因为：
1. 设备已经绑定但用户不知道
2. 之前绑定失败但本地数据库有残留
3. 多次点击绑定按钮导致重复操作

### Q2: 清除APP数据会丢失什么？

**A**: 会清除：
- 本地缓存的健康数据
- 登录状态
- 设备绑定记录

不会丢失：
- 服务器上的数据（重新登录后会同步）
- 账号信息

### Q3: 如何避免这个问题？

**A**: 
1. 绑定前检查设备状态
2. 不要重复点击绑定按钮
3. 如果绑定失败，先刷新再重试

### Q4: 能否同时绑定多个手环？

**A**: 取决于系统设计：
- 如果允许多设备：每个用户可以绑定多个手环
- 如果单设备模式：每个用户只能绑定一个手环

## 快速修复命令

### 检查设备状态
```bash
# 查看所有设备
curl http://localhost:8000/api/v1/devices

# 查看特定设备
curl http://localhost:8000/api/v1/devices/53:57:08:XX:XX:XX
```

### 解绑设备（需要管理员权限）
```bash
curl -X POST http://localhost:8000/api/v1/devices/unbind \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -d '{
    "mac_address": "53:57:08:XX:XX:XX",
    "operator_id": "admin",
    "reason": "fix_binding_error"
  }'
```

### 数据库直接修复
```bash
# 备份数据库
cp data/app.db data/app.db.backup

# 修复绑定
sqlite3 data/app.db "UPDATE devices SET user_id = NULL, bind_status = 'unbound' WHERE mac_address = '53:57:08:XX:XX:XX';"
```

## 总结

**最简单的解决方法**：
1. 在APP中找到该设备
2. 先解绑
3. 再重新绑定

**如果找不到设备**：
1. 清除APP数据
2. 重新登录
3. 重新绑定

**如果还是不行**：
1. 联系管理员
2. 在后端解绑设备
3. 然后在APP中绑定
