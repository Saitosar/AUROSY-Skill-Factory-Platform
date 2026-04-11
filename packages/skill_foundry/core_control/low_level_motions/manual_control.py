import pygame
import sys
import os

# Подключение путей SAI Platform
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path: sys.path.append(root_dir)

from core_control.joint_controller import JointController
from core_control.state_listener import StateListener

TARGET_JOINT = 15 
MOVE_SPEED = 0.01

def main():
    pygame.init()
    screen = pygame.display.set_mode((200, 200))
    pygame.display.set_caption("SAI Manual Control")
    
    ctrl = JointController()
    listener = StateListener()
    listener.wait_for_ready()
    
    current_q = listener.get_joint_pos(TARGET_JOINT)
    
    print(f"\n[SAI] Контроль: {ctrl.JOINT_MAP.get(TARGET_JOINT)}")
    print("ИСПОЛЬЗУЙ СТРЕЛКИ ВВЕРХ/ВНИЗ. ESC для выхода.")

    clock = pygame.time.Clock()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False

        keys = pygame.key.get_pressed()
        if keys[pygame.K_UP]: current_q += MOVE_SPEED
        if keys[pygame.K_DOWN]: current_q -= MOVE_SPEED
        if keys[pygame.K_ESCAPE]: running = False

        ctrl.set_joint(TARGET_JOINT, current_q)
        ctrl.publish()
        
        real_q = listener.get_joint_pos(TARGET_JOINT)
        print(f"Команда: {current_q:.3f} | Реальность: {real_q:.3f}", end="\r")
        clock.tick(100)

    pygame.quit()

if __name__ == "__main__":
    main()