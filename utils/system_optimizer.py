"""
系统优化检测和配置工具
检查硬件加速、多线程配置等性能优化选项
"""
import os
import platform
import multiprocessing
import subprocess
import json
from typing import Dict, List, Tuple, Optional


class SystemOptimizer:
    """系统性能优化检测和配置"""
    
    def __init__(self):
        self.system_info = self._detect_system_info()
        self.optimization_report = {}
    
    def _detect_system_info(self) -> Dict:
        """检测系统基本信息"""
        info = {
            'platform': platform.system(),
            'architecture': platform.architecture()[0],
            'cpu_count': multiprocessing.cpu_count(),
            'machine': platform.machine(),
            'processor': platform.processor(),
        }
        
        if info['platform'] == 'Darwin':  # macOS
            try:
                # 获取Mac硬件信息
                result = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    info['cpu_model'] = result.stdout.strip()
                
                # 检查是否是Apple Silicon
                result = subprocess.run(['sysctl', '-n', 'hw.optional.arm64'], 
                                      capture_output=True, text=True)
                info['is_apple_silicon'] = result.returncode == 0 and result.stdout.strip() == '1'
                
                # 获取内存信息
                result = subprocess.run(['sysctl', '-n', 'hw.memsize'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    memory_bytes = int(result.stdout.strip())
                    info['memory_gb'] = round(memory_bytes / (1024**3), 1)
                    
            except Exception as e:
                print(f"Warning: Could not detect macOS hardware details: {e}")
        
        return info
    
    def check_hardware_acceleration(self) -> Dict:
        """检查硬件加速支持情况"""
        acceleration_info = {
            'gpu_available': False,
            'metal_support': False,
            'videotoolbox_support': False,
            'recommendations': []
        }
        
        if self.system_info['platform'] == 'Darwin':  # macOS
            # 检查Metal支持（Apple GPU加速）
            try:
                result = subprocess.run(['system_profiler', 'SPDisplaysDataType', '-json'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    display_data = json.loads(result.stdout)
                    for item in display_data.get('SPDisplaysDataType', []):
                        if 'sppci_model' in item:
                            acceleration_info['gpu_available'] = True
                            if 'Apple' in item.get('sppci_model', ''):
                                acceleration_info['metal_support'] = True
                            break
            except Exception as e:
                print(f"Warning: Could not detect GPU info: {e}")
            
            # VideoToolbox总是在macOS上可用
            acceleration_info['videotoolbox_support'] = True
            
            # 生成建议
            if acceleration_info['metal_support']:
                acceleration_info['recommendations'].append("✅ Apple Silicon GPU detected - optimal performance expected")
            elif acceleration_info['gpu_available']:
                acceleration_info['recommendations'].append("⚠️ Intel GPU detected - moderate acceleration available")
            
            if acceleration_info['videotoolbox_support']:
                acceleration_info['recommendations'].append("✅ VideoToolbox available for video processing")
        
        return acceleration_info
    
    def get_optimal_thread_config(self) -> Dict:
        """获取最优线程配置"""
        cpu_count = self.system_info['cpu_count']
        
        config = {
            'whisper_threads': min(8, cpu_count),  # Whisper处理线程
            'translation_threads_openai': min(9, max(3, (cpu_count // 4) * 3)),  # OpenAI翻译线程 - 增加三倍
            'translation_threads_google': min(15, max(6, (cpu_count // 2) * 3)),  # Google翻译线程 - 增加三倍
            'main_thread_pool': min(4, max(2, cpu_count // 2)),  # 主线程池
            'reasoning': []
        }
        
        # Apple Silicon优化
        if self.system_info.get('is_apple_silicon', False):
            config['whisper_threads'] = min(10, cpu_count)  # Apple Silicon对AI任务优化更好
            config['translation_threads_openai'] = min(18, (cpu_count // 3) * 4)  # Apple Silicon优化
            config['translation_threads_google'] = min(30, (cpu_count // 2) * 4)  # Apple Silicon优化
            config['reasoning'].append("🍎 Apple Silicon detected - increased Whisper and translation threads for ML optimization")
        
        # 高核心数CPU优化
        if cpu_count >= 8:
            config['translation_threads_openai'] = min(15, (cpu_count // 3) * 3)  # 进一步增加高核心CPU的翻译线程
            config['translation_threads_google'] = min(24, (cpu_count // 2) * 3)  # 进一步增加高核心CPU的翻译线程
            config['reasoning'].append(f"🚀 High-core CPU ({cpu_count} cores) - increased translation parallelism (3x boost)")
        elif cpu_count <= 4:
            config['translation_threads_openai'] = 6  # 即使在低核心数也保持较高的线程数
            config['translation_threads_google'] = 9  # 即使在低核心数也保持较高的线程数
            config['main_thread_pool'] = 2
            config['reasoning'].append(f"⚠️ Limited cores ({cpu_count}) - but still using boosted translation threads for better throughput")
        
        # 内存考虑
        memory_gb = self.system_info.get('memory_gb', 8)
        if memory_gb < 8:
            config['whisper_threads'] = min(4, config['whisper_threads'])
            config['main_thread_pool'] = min(2, config['main_thread_pool'])
            config['reasoning'].append(f"💾 Limited memory ({memory_gb}GB) - reduced threading to prevent swapping")
        elif memory_gb >= 16:
            config['reasoning'].append(f"💾 Adequate memory ({memory_gb}GB) - full threading capacity available")
        
        return config
    
    def check_dependencies(self) -> Dict:
        """检查关键依赖和配置"""
        deps_info = {
            'ffmpeg_available': False,
            'ffmpeg_hardware_support': False,
            'whisper_model_available': False,
            'issues': [],
            'recommendations': []
        }
        
        # 检查FFmpeg
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                deps_info['ffmpeg_available'] = True
                
                # 检查硬件加速支持
                if 'videotoolbox' in result.stdout.lower():
                    deps_info['ffmpeg_hardware_support'] = True
                    deps_info['recommendations'].append("✅ FFmpeg with VideoToolbox acceleration detected")
                else:
                    deps_info['issues'].append("⚠️ FFmpeg found but no hardware acceleration detected")
                    
        except Exception:
            deps_info['issues'].append("❌ FFmpeg not found - video processing will fail")
        
        # 检查Whisper模型
        model_paths = [
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "ggml-distil-large-v3.5.bin"),
            os.path.expanduser("~/.whisper_models/ggml-distil-large-v3.5.bin")
        ]
        
        for model_path in model_paths:
            if os.path.exists(model_path):
                deps_info['whisper_model_available'] = True
                deps_info['recommendations'].append(f"✅ Whisper model found at: {model_path}")
                break
        else:
            deps_info['issues'].append("⚠️ Whisper model not found - will download on first use")
        
        return deps_info
    
    def generate_optimization_report(self) -> str:
        """生成完整的优化报告"""
        hw_accel = self.check_hardware_acceleration()
        thread_config = self.get_optimal_thread_config()
        deps_info = self.check_dependencies()
        
        report = []
        report.append("=" * 60)
        report.append("🔧 SYSTEM OPTIMIZATION REPORT")
        report.append("=" * 60)
        
        # 系统信息
        report.append("\n📋 SYSTEM INFORMATION:")
        report.append(f"  Platform: {self.system_info['platform']} ({self.system_info['architecture']})")
        report.append(f"  CPU: {self.system_info.get('cpu_model', 'Unknown')} ({self.system_info['cpu_count']} cores)")
        if 'memory_gb' in self.system_info:
            report.append(f"  Memory: {self.system_info['memory_gb']} GB")
        if self.system_info.get('is_apple_silicon'):
            report.append("  🍎 Apple Silicon detected")
        
        # 硬件加速
        report.append("\n🚀 HARDWARE ACCELERATION:")
        if hw_accel['recommendations']:
            for rec in hw_accel['recommendations']:
                report.append(f"  {rec}")
        else:
            report.append("  ⚠️ No hardware acceleration detected")
        
        # 线程配置
        report.append("\n⚙️ OPTIMAL THREAD CONFIGURATION:")
        report.append(f"  Whisper Processing: {thread_config['whisper_threads']} threads")
        report.append(f"  OpenAI Translation: {thread_config['translation_threads_openai']} threads")
        report.append(f"  Google Translation: {thread_config['translation_threads_google']} threads")
        report.append(f"  Main Thread Pool: {thread_config['main_thread_pool']} threads")
        
        if thread_config['reasoning']:
            report.append("\n💡 OPTIMIZATION REASONING:")
            for reason in thread_config['reasoning']:
                report.append(f"  {reason}")
        
        # 依赖检查
        report.append("\n🔗 DEPENDENCIES STATUS:")
        if deps_info['recommendations']:
            for rec in deps_info['recommendations']:
                report.append(f"  {rec}")
        if deps_info['issues']:
            for issue in deps_info['issues']:
                report.append(f"  {issue}")
        
        # 性能建议
        report.append("\n🎯 PERFORMANCE RECOMMENDATIONS:")
        
        if self.system_info['cpu_count'] >= 8:
            report.append("  ✅ High-performance CPU detected - expect fast processing")
        elif self.system_info['cpu_count'] <= 4:
            report.append("  ⚠️ Limited CPU cores - consider processing fewer files simultaneously")
        
        if self.system_info.get('memory_gb', 8) >= 16:
            report.append("  ✅ Adequate memory for concurrent processing")
        else:
            report.append("  ⚠️ Limited memory - avoid processing too many large files at once")
        
        if hw_accel['metal_support']:
            report.append("  ✅ Apple Silicon GPU - optimal for AI workloads")
        elif not hw_accel['gpu_available']:
            report.append("  ⚠️ No dedicated GPU - CPU-only processing expected")
        
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)
    
    def get_optimized_config(self) -> Dict:
        """获取优化后的配置参数"""
        thread_config = self.get_optimal_thread_config()
        hw_accel = self.check_hardware_acceleration()
        
        return {
            'whisper_threads': thread_config['whisper_threads'],
            'openai_workers': thread_config['translation_threads_openai'],
            'google_workers': thread_config['translation_threads_google'],
            'main_pool_size': thread_config['main_thread_pool'],
            'use_hardware_accel': hw_accel['videotoolbox_support'],
            'system_info': self.system_info,
        }


def print_system_report():
    """便捷函数：打印系统优化报告"""
    optimizer = SystemOptimizer()
    print(optimizer.generate_optimization_report())
    return optimizer.get_optimized_config()


if __name__ == "__main__":
    print_system_report()
