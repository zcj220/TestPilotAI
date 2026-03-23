Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "NoteApp")
$win = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)

function Get-Children($el, $depth) {
    if ($depth -gt 4) { return }
    $children = $el.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($c in $children) {
        $indent = "  " * $depth
        $n = $c.Current.Name
        $cls = $c.Current.ClassName
        $aid = $c.Current.AutomationId
        $ct = $c.Current.ControlType.ProgrammaticName
        Write-Output "$indent[$ct] Name='$n' Class='$cls' AutomationId='$aid'"
        Get-Children $c ($depth + 1)
    }
}

if ($null -ne $win) {
    Write-Output "Found: $($win.Current.Name) hwnd=$($win.Current.NativeWindowHandle)"
    Get-Children $win 1
}
else {
    Write-Output "NOT FOUND - NoteApp window not detected"
}
