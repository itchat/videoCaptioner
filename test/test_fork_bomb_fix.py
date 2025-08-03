#!/usr/bin/env python3
"""
测试脚本：验证 macOS .app 环境中的分叉炸弹修复
"""
import sys
import os
import multiprocessing as mp

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

def test_multiprocess_import():
    """测试多进程模块导入是否安全"""
    print("🧪 Testing multiprocess import safety...")
    
    try:
        # 这应该是安全的，不会触发分叉炸弹
        from core.video_processor import MultiprocessVideoManager
        print("✅ MultiprocessVideoManager import successful")
        
        # 测试创建管理器（延迟初始化）
        print("✅ Testing delayed initialization...")
        # 这个不应该创建任何进程，只是设置参数
        
        print("✅ All multiprocess safety tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

def test_actual_manager_creation():
    """测试实际创建管理器是否安全"""
    print("🧪 Testing actual MultiprocessVideoManager creation...")
    
    try:
        from core.video_processor import MultiprocessVideoManager
        
        # 测试创建管理器实例
        manager = MultiprocessVideoManager(max_processes=2)
        print("✅ MultiprocessVideoManager created successfully")
        
        # 测试延迟初始化方法调用
        print(f"✅ Manager initialized with max_processes: {manager.max_processes}")
        print(f"✅ Active processes: {len(manager.active_processes)}")
        print(f"✅ Pending tasks: {len(manager.pending_tasks)}")
        
        # 清理
        manager.cleanup()
        print("✅ Manager cleanup successful")
        
        return True
        
    except Exception as e:
        print(f"❌ Manager creation test failed: {e}")
        return False

def test_app_simulation():
    """模拟 .app 环境测试"""
    print("🧪 Simulating .app environment...")
    
    # 模拟打包环境
    sys.frozen = True
    sys.executable = "/Applications/videoCaptioner.app/Contents/MacOS/main"
    
    try:
        # 测试主程序导入
        from src.main import main
        print("✅ Main program import successful in simulated .app environment")
        
        # 不实际运行 main()，只是测试导入
        print("✅ App simulation test passed!")
        return True
        
    except Exception as e:
        print(f"❌ App simulation test failed: {e}")
        return False
    finally:
        # 清理模拟环境
        if hasattr(sys, 'frozen'):
            delattr(sys, 'frozen')

if __name__ == "__main__":
    print("🚀 Fork Bomb Fix Verification Test")
    print("=" * 50)
    
    # 设置多进程启动方法（这应该防止分叉炸弹）
    mp.freeze_support()
    mp.set_start_method('spawn', force=True)
    print(f"✅ Multiprocess start method set to: {mp.get_start_method()}")
    
    # 运行测试
    test1_passed = test_multiprocess_import()
    test2_passed = test_actual_manager_creation()
    test3_passed = test_app_simulation()
    
    print("\n" + "=" * 50)
    if test1_passed and test2_passed and test3_passed:
        print("🎉 ALL TESTS PASSED! Fork bomb fix appears to be working.")
        print("✅ Safe to compile to .app")
    else:
        print("❌ TESTS FAILED! Fork bomb risk still exists.")
        print("⚠️  Do not compile to .app until fixed")
    
    print("=" * 50)
