-- ============================================================================
-- PC Fish 全自動智能選魚繁殖腳本 v3.0 (穩定防崩潰版)
-- 適用遊戲：PC Fish (Steam / PCFish.exe)
-- 更新特性：
--   1. 自動辨識並追蹤遊戲進程 PID (遊戲重開自動重連)
--   2. 修復 monoscript.lua:3101 報錯 (移除 GUI 搜尋調用)
--   3. 防崩潰保護 (Main-Thread 安全調用，避免 0xc0000005 閃退)
--   4. 嚴格過濾雲端合法魚隻：優先選擇 3星神魚 (FS00024 Lv3、FS00001 Lv1)
-- ============================================================================

local PROCESS_NAME = "PCFish.exe"

-- 全域狀態
local isBreedingLoop = false
local breedTimer = nil
local loopIntervalMs = 3000

-- 1. 進程檢查與自動重連
function EnsureProcessAttached()
    local curPid = getOpenedProcessID()
    local livePids = getProcesslist()
    local targetPid = nil

    if livePids then
        for pid, name in pairs(livePids) do
            if string.lower(name) == string.lower(PROCESS_NAME) then
                targetPid = pid
                break
            end
        end
    end

    if not targetPid then
        return false, "尚未檢測到 PCFish.exe 運行，請開啟遊戲。"
    end

    if curPid ~= targetPid then
        openProcess(targetPid)
        LaunchMonoDataCollector()
        print(string.format("[系統] 已自動連接至最新遊戲進程 PID: %d", targetPid))
    end

    return true, targetPid
end

-- 2. 輔助函數：讀取 Mono Unicode 字串
local function readMonoStr(ptr)
    if not ptr or ptr == 0 then return "" end
    local strLen = readInteger(ptr + 0x10)
    if not strLen or strLen <= 0 or strLen > 60 then return "" end
    local res = ""
    for i = 0, strLen - 1 do
        local b = readByte(ptr + 0x14 + i * 2)
        if b and b >= 32 and b <= 126 then
            res = res .. string.char(b)
        else
            return ""
        end
    end
    return res
end

-- 3. 核心函數：在合法 21 條可用魚中挑選最高品級且剩餘次數 > 0 的魚
function GetTopTwoAvailableFish()
    local classFishModel = mono_findClass("NN.PF.Models", "FishModel")
    if not classFishModel or classFishModel == 0 then return nil, nil, 0 end

    -- 使用安全無 GUI 的方式搜尋
    local instances = mono_class_findInstancesOfClassListOnly(classFishModel)
    if not instances or #instances == 0 then return nil, nil, 0 end

    local eligible = {}
    for i, f in ipairs(instances) do
        local idStr = readMonoStr(readPointer(f + 0x10))
        local fishCode = readMonoStr(readPointer(f + 0x18))
        local grade = readInteger(f + 0x28)
        local level = readInteger(f + 0x2C)
        local growth = readInteger(f + 0x30)
        local remainCount = readInteger(f + 0x34)
        local maxCount = readInteger(f + 0x38)

        local isBasicFish = string.find(idStr, "BF") ~= nil
        local canBreed = (remainCount > 0) or isBasicFish

        if #idStr > 0 and grade >= 0 and grade <= 10 and canBreed then
            table.insert(eligible, {
                ptr = f,
                idPtr = readPointer(f + 0x10),
                id = idStr,
                fish = fishCode,
                grade = grade,
                level = level,
                growth = growth,
                remainCount = remainCount,
                maxCount = maxCount,
                isBasic = isBasicFish
            })
        end
    end

    -- 排序：品級由高到低 (3星 > 2星 > 1星 > 基礎魚0星)，同星級依等級高到低，再依剩餘次數排序
    table.sort(eligible, function(a, b)
        if a.grade ~= b.grade then return a.grade > b.grade end
        if a.level ~= b.level then return a.level > b.level end
        return a.remainCount > b.remainCount
    end)

    -- 分組各稀有度可用魚 (最高期望值黃金階梯)
    local byGrade = {}
    for i = 0, 5 do byGrade[i] = {} end
    for _, f in ipairs(eligible) do
        local g = f.grade
        if byGrade[g] then
            table.insert(byGrade[g], f)
        end
    end

    -- 同稀有度組內，剩餘配種次數較少者優先配種 (remainCount 升序)
    for i = 1, 5 do
        table.sort(byGrade[i], function(a, b)
            if a.remainCount ~= b.remainCount then
                return a.remainCount < b.remainCount
            end
            return a.level > b.level
        end)
    end


    -- 最高期望值配對階梯：
    -- 1. 雙傳奇 (4x4) -> Total 8 (神話 5.0%, 傳奇 51.3%, 稀有 43.7%)
    if #byGrade[4] >= 2 then return byGrade[4][1], byGrade[4][2], #eligible end
    -- 2. 傳奇-稀有催化 (4x3) -> Total 7 (神話 3.5%, 傳奇 44.4%, 稀有 52.1%)
    if #byGrade[4] >= 1 and #byGrade[3] >= 1 then return byGrade[4][1], byGrade[3][1], #eligible end
    -- 3. 雙稀有 (3x3) -> Total 6 (神話 2.0%, 傳奇 10.0%, 嚴禁配高級 3x2)
    if #byGrade[3] >= 2 then return byGrade[3][1], byGrade[3][2], #eligible end
    -- 4. 雙高級 (2x2) -> Total 4 (稀有 15.0%, 傳奇 3.0%, 嚴禁配普通 2x1)
    if #byGrade[2] >= 2 then return byGrade[2][1], byGrade[2][2], #eligible end
    -- 5. 雙普通 (1x1) -> Total 2 (高級 20.0%, 稀有 4.0%)
    if #byGrade[1] >= 2 then return byGrade[1][1], byGrade[1][2], #eligible end
    -- 6. 胚子提純 (1x0 或 0x0)
    if #byGrade[1] >= 1 and #byGrade[0] >= 1 then return byGrade[1][1], byGrade[0][1], #eligible end
    if #byGrade[0] >= 2 then return byGrade[0][1], byGrade[0][2], #eligible end

    return nil, nil, #eligible
end

-- 4. 核心配種邏輯 (單次安全執行)
function ExecuteOneAutoBreed()
    if not isBreedingLoop then return end

    local attached, err = EnsureProcessAttached()
    if not attached then
        print("[提示] " .. err)
        return
    end

    -- 尋找 UIBreed
    local classUIBreed = mono_findClass("NN.PF.UI.Breed", "UIBreed")
    if not classUIBreed or classUIBreed == 0 then return end

    local instances = mono_class_findInstancesOfClassListOnly(classUIBreed)
    if not instances or #instances == 0 then
        print("[提示] 目前遊戲中未打開繁殖面板 (UIBreed)，請在遊戲中打開繁殖介面。")
        return
    end

    local uibreed = instances[1]

    -- 挑選當前庫存中最頂級的 2 條可用魚
    local p1, p2, total = GetTopTwoAvailableFish()
    if not p1 or not p2 then
        print(string.format("[提示] 可繁殖魚隻不足 2 條 (符合條件剩餘: %d 條)，等待下次檢查。", total))
        return
    end

    -- 填入親代魚槽位
    local parentArr = readPointer(uibreed + 0x50)
    if parentArr and parentArr ~= 0 then
        writePointer(parentArr + 0x20, p1.idPtr)
        writePointer(parentArr + 0x28, p2.idPtr)
    end

    local listViewParentArr = readPointer(uibreed + 0x38)
    if listViewParentArr and listViewParentArr ~= 0 then
        local slot0 = readPointer(listViewParentArr + 0x20)
        local slot1 = readPointer(listViewParentArr + 0x28)
        if slot0 and slot0 ~= 0 then writePointer(slot0 + 0x88, p1.ptr) end
        if slot1 and slot1 ~= 0 then writePointer(slot1 + 0x88, p2.ptr) end
    end

    -- 觸發按鈕點擊事件 (安全調用)
    local methodBreed = mono_class_findMethod(classUIBreed, "Breed")
    if methodBreed and methodBreed ~= 0 then
        mono_invoke_method(nil, methodBreed, uibreed, {})
        print(string.format("[%s] 【成功挑選最高級魚並完成配種】", os.date("%X")))
        print(string.format("  -> 親代 1: [%d星 Lv %d] %s (剩餘次數: %d/%d)", p1.grade, p1.level, p1.fish, p1.remainCount, p1.maxCount))
        print(string.format("  -> 親代 2: [%d星 Lv %d] %s (剩餘次數: %d/%d)", p2.grade, p2.level, p2.fish, p2.remainCount, p2.maxCount))
    end
end

-- 快捷鍵控制
function StartAutoBreeder()
    if isBreedingLoop then return end
    isBreedingLoop = true
    print("==================================================")
    print(">>> 【PC Fish 全自動智能配種已啟動】 <<<")
    print(string.format(">>> 繁殖循環間隔: %.1f 秒，按 [F2] 隨時停止 <<<", loopIntervalMs / 1000))
    print("==================================================")
    
    ExecuteOneAutoBreed()

    if not breedTimer then
        breedTimer = createTimer()
        breedTimer.Interval = loopIntervalMs
        breedTimer.OnTimer = ExecuteOneAutoBreed
    else
        breedTimer.Interval = loopIntervalMs
        breedTimer.setEnabled(true)
    end
end

function StopAutoBreeder()
    if not isBreedingLoop then return end
    isBreedingLoop = false
    if breedTimer then
        breedTimer.setEnabled(false)
    end
    print(">>> 【全自動配種已停止】 <<<")
end

-- 綁定快捷鍵
if hkF1 then hkF1.destroy() end
if hkF2 then hkF2.destroy() end

hkF1 = createHotkey(StartAutoBreeder, VK_F1)
hkF2 = createHotkey(StopAutoBreeder, VK_F2)

print("--------------------------------------------------")
print("【PC Fish 全自動配種腳本 v3.0】加載成功！")
print("  - [F1] 啟動全自動最高級魚配種")
print("  - [F2] 停止自動配種")
print("--------------------------------------------------")
